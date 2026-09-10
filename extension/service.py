"""Bounded local HTTP service with process-affine sessions and per-request deadlines."""
from __future__ import annotations
import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from extension.common import ARTIFACTS, ROOT


def worker(input_queue, output_queue, catalog_path, snapshot, ttl, variant, catalog_updates=False, worker_id=None):
    from extension.catalog import Catalog
    from extension.agent import Agent
    from extension.vectors import VectorIndex
    started=time.perf_counter()
    store=Catalog(catalog_path)
    from extension.factory import create
    agent=create(store,variant,worker_id=worker_id);vectors=agent.vectors
    seen, touched, sequence = OrderedDict(), {}, {}
    output_queue.put({'ready': True, 'startup_seconds': time.perf_counter() - started})
    while True:
        request = input_queue.get()
        if request is None:
            break
        began = time.perf_counter();cached_retry=False
        token = request['token']
        sid = request.get('session_id', '')
        now = time.monotonic()
        for expired in [s for s, stamp in touched.items() if now - stamp > ttl]:
            agent.close(expired) if hasattr(agent, 'close') else agent._sessions.pop(expired, None)
            touched.pop(expired, None)
            sequence.pop(expired, None)
            for key in [key for key in seen if key[0] == expired]:
                seen.pop(key)
        try:
            if time.perf_counter() > request['deadline']:
                result, status = {'error': 'deadline_exceeded_before_execution'}, 504
            elif request['operation'] == 'sync':
                store.sync(request['minimum_version'])
                if vectors is not None:vectors.sync(store)
                result,status={'catalog_version':store.version},200
            elif request['operation'] == 'reset':
                agent.reset(sid, request.get('user_profile', {}))
                sequence[sid] = 0
                for key in [key for key in seen if key[0] == sid]:
                    seen.pop(key)
                result, status = {'reset': True}, 200
            elif request['operation'] == 'close':
                agent.close(sid) if hasattr(agent, 'close') else agent._sessions.pop(sid, None)
                touched.pop(sid, None)
                sequence.pop(sid, None)
                for key in [key for key in seen if key[0] == sid]:
                    seen.pop(key)
                result, status = {'closed': True}, 200
            elif request['operation'] == 'respond':
                key = (sid, request['request_id'])
                body_hash = hashlib.sha256(json.dumps({k: request[k] for k in ('turn','message','top_k')}, sort_keys=True).encode()).hexdigest()
                if key in seen:
                    cached_retry=True
                    store.sync(request.get('minimum_version'))
                    prior_hash, result = seen[key]
                    status = 200 if prior_hash == body_hash else 409
                    if status == 409:
                        result = {'error': 'request_id_reused_with_different_body'}
                elif sid not in agent.states:
                    result, status = {'error': 'session_missing_or_expired'}, 404
                elif request['turn'] != sequence[sid] + 1:
                    result, status = {'error': 'turn_out_of_order'}, 409
                else:
                    agent.request_deadline=request['deadline']
                    result = agent.respond(sid, request['message'], request['turn'], request['top_k'])
                    status = 200
                    sequence[sid] = request['turn']
                    seen[key] = (body_hash, result)
                    if len(seen) > 20000:
                        seen.popitem(last=False)
            else:
                result, status = {'error': 'unknown_operation'}, 400
            if store is not None and 'recommendations' in result:
                result = {**result, 'catalog_version':store.version, 'recommendations':[r for r in result['recommendations'] if r['parent_asin'] in store.products and store.products[r['parent_asin']].get('available',True)]}
            if sid in agent.states:
                touched[sid] = now
        except (ValueError, KeyError, TypeError) as exc:
            result, status = {'error': 'invalid_request', 'detail': str(exc)}, 400
        except Exception as exc:
            result, status = {'error': type(exc).__name__, 'detail': str(exc)}, 500
        output_queue.put({'token': token, 'status': status, 'result': result, 'queue_ms': (began - request['enqueued']) * 1000, 'service_ms': (time.perf_counter() - began) * 1000, 'route_trace':({**agent.trace.get(sid,{}),'cache_origin_version':agent.trace.get(sid,{}).get('version'),'version':store.version,'cached_retry':True} if cached_retry else agent.trace.get(sid)) if status==200 and request['operation']=='respond' else None})
    if vectors is not None:vectors.close()
    store.close()


class Pool:
    def __init__(self, count, catalog, snapshot=None, capacity=64, ttl=900, variant='main', catalog_updates=False):
        self.catalog=catalog
        self.publication_queue=queue.Queue(maxsize=8)
        self.coordinator_ready=threading.Event()
        self.published_version=0
        self.workers, self.inputs, self.pending = [], [], {}
        self.lock = threading.Lock()
        self.out = mp.Queue()
        self.ready = []
        self.stopping = False
        for worker_id in range(count):
            incoming = mp.Queue(maxsize=capacity)
            process = mp.Process(target=worker, args=(incoming, self.out, str(catalog), str(snapshot) if snapshot else None, ttl, variant, catalog_updates, worker_id), daemon=True)
            process.start()
            self.inputs.append(incoming)
            self.workers.append(process)
        threading.Thread(target=self.collect, daemon=True).start()
        self.coordinator=threading.Thread(target=self.coordinate,daemon=True);self.coordinator.start()

    def collect(self):
        while not self.stopping:
            try:
                result = self.out.get(timeout=1)
            except queue.Empty:
                continue
            if result.get('ready'):
                self.ready.append(result)
            else:
                with self.lock:
                    waiter = self.pending.get(result['token'])
                if waiter:
                    waiter.put(result)

    def submit(self, body, slot=None):
        slot = slot if slot is not None else int.from_bytes(hashlib.sha256(body['session_id'].encode()).digest()[:4], 'big') % len(self.workers)
        if not self.workers[slot].is_alive():
            return {'status': 503, 'result': {'error': 'worker_unavailable'}}
        token = uuid.uuid4().hex
        waiter = queue.Queue(maxsize=1)
        timeout = min(30, max(.01, float(body.get('timeout_seconds', 5))))
        started = time.perf_counter()
        request = {'minimum_version':self.published_version,**body, 'token': token, 'enqueued': started, 'deadline': started + timeout}
        with self.lock:
            self.pending[token] = waiter
        try:
            self.inputs[slot].put_nowait(request)
            return waiter.get(timeout=timeout)
        except queue.Full:
            return {'status': 429, 'result': {'error': 'queue_full'}}
        except queue.Empty:
            return {'status': 504, 'result': {'error': 'deadline_exceeded'}}
        finally:
            with self.lock:
                self.pending.pop(token, None)

    def coordinate(self):
        from extension.catalog import Catalog
        store=Catalog(self.catalog);self.published_version=store.version;self.coordinator_ready.set()
        try:
            while not self.stopping:
                try:events,reply=self.publication_queue.get(timeout=.5)
                except queue.Empty:continue
                try:
                    version=store.apply(events)
                    with ThreadPoolExecutor(max_workers=len(self.workers)) as executor:
                        results=list(executor.map(lambda i:self.submit({'session_id':'publication','operation':'sync','minimum_version':version,'timeout_seconds':30},slot=i),range(len(self.workers))))
                    if any(r['status']!=200 for r in results):
                        result={'status':503,'result':{'error':'worker_publication_incomplete','committed_version':version,'workers':results}}
                    else:
                        self.published_version=version
                        result={'status':200,'result':{'catalog_version':version,'worker_acknowledgements':[r['result']['catalog_version'] for r in results]}}
                except Exception as exc:result={'status':400,'result':{'error':type(exc).__name__,'detail':str(exc)}}
                reply.put(result)
        finally:store.close()

    def publish(self,events):
        reply=queue.Queue(maxsize=1)
        try:
            self.publication_queue.put_nowait((events,reply));return reply.get(timeout=120)
        except queue.Full:return {'status':429,'result':{'error':'publication_queue_full'}}
        except queue.Empty:return {'status':504,'result':{'error':'publication_ack_timeout'}}

    def close(self):
        self.stopping = True
        self.coordinator.join(timeout=5)
        for p in self.workers:
            if p.is_alive():
                p.terminate()
            p.join(timeout=5)


def serve(port, workers, catalog, variant='rules'):
    # Bound BLAS work per worker before Windows spawns fresh interpreters.
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    from extension.catalog import Catalog
    initialized=Catalog(catalog,ARTIFACTS/'catalog/catalog-60000.jsonl');initialized.checkpoint();initialized.close()
    pool=Pool(workers,catalog,variant=variant,catalog_updates=True)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        def do_GET(self):
            alive = all(p.is_alive() for p in pool.workers)
            ready = len(pool.ready) == workers and alive and pool.coordinator_ready.is_set()
            self.reply(200 if ready else 503, {'ready': ready, 'workers': workers, 'startup': pool.ready})
        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('Body size outside bounds')
                body = json.loads(self.rfile.read(length))
                operation = self.path.strip('/')
                if operation not in ('reset', 'respond', 'close') + ('catalog_update',):
                    raise ValueError('Unknown operation')
                sid = body['session_id']
                if not isinstance(sid, str) or not 0 < len(sid) <= 128:
                    raise ValueError('Invalid session id')
                body['operation'] = operation
                if operation == 'catalog_update' and (not isinstance(body.get('events'),list) or not 1 <= len(body['events']) <= 5000):
                    raise ValueError('Update batch must contain 1 to 5000 events')
                if operation == 'respond':
                    if not isinstance(body.get('message'), str) or len(body['message']) > 8192:
                        raise ValueError('Invalid message')
                    if not isinstance(body.get('turn'), int) or not 1 <= body['turn'] <= 100:
                        raise ValueError('Invalid turn')
                    body['top_k'] = min(10, max(1, int(body.get('top_k', 10))))
                    if not isinstance(body.get('request_id'), str):
                        raise ValueError('Request id required')
                result = pool.publish(body['events']) if operation=='catalog_update' else pool.submit(body)
                self.reply(result['status'], result)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.reply(400, {'error': str(exc)})
    class Server(ThreadingHTTPServer):
        request_queue_size = 256
        def __init__(self, *args):
            super().__init__(*args)
            self.slots = threading.BoundedSemaphore(512)
        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                body = b'{"error":"connection_limit"}'
                try:
                    request.sendall(b'HTTP/1.1 429 Too Many Requests\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                finally:
                    self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.slots.release()
                raise
        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()
    server = Server(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.request_queue_size = 256
    try:
        server.serve_forever()
    finally:
        server.server_close()
        pool.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8092)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--catalog',type=Path,default=ARTIFACTS/'stores/service')
    parser.add_argument('--variant', choices=['rules','lexical','hybrid','graph','tinybert','tinybert-lexical','tinybert-100','gated-tinybert','minilm-cross','learned','residual','rag','rag-local','rag-passages','rag-passages-local','corrected-lexical','rag-passages-corrected','rag-passages-local-corrected'],default='rules')
    args = parser.parse_args()
    serve(args.port,args.workers,args.catalog,args.variant)
