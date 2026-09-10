"""Actual LightRAG insertion/deletion pilot using local Qwen and MiniLM."""
import argparse
import asyncio
import importlib.metadata
import json
import random
import time
import sys
import psutil
from extension.common import ARTIFACTS, ROOT, read_jsonl, write_json, manifest
from extension.models import LocalLLM, Embeddings

async def run(size, seconds):
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    from lightrag.kg.shared_storage import initialize_pipeline_status
    products = read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')
    random.Random(20260910).shuffle(products)
    products = products[:size]
    folder = ARTIFACTS / 'updates' / f'lightrag-{size}'
    if (folder/'storage').exists():raise RuntimeError('Clean LightRAG pilot requires a fresh storage directory')
    folder.mkdir(parents=True, exist_ok=True)
    from extension.common import write_jsonl
    write_jsonl(folder/'shared-products.jsonl',products)
    embedder = Embeddings()
    llm = LocalLLM(timeout=120)
    calls = []
    async def embedding(texts):
        return await asyncio.to_thread(embedder.encode, texts)
    async def completion(prompt, system_prompt=None, history_messages=None, **kwargs):
        start = time.perf_counter()
        content = (system_prompt or '') + '\n' + '\n'.join(str(x.get('content','')) for x in history_messages or []) + '\n' + prompt
        text, usage = await asyncio.to_thread(llm.complete, content, 512)
        calls.append({'seconds': time.perf_counter() - start, 'usage': usage})
        return text
    rag = LightRAG(working_dir=str(folder / 'storage'), embedding_func=EmbeddingFunc(embedding_dim=384, max_token_size=256, func=embedding), llm_model_func=completion, llm_model_name='local-Qwen3-4B-Q4_K_M', llm_model_max_async=1, embedding_func_max_async=1, max_parallel_insert=1, entity_extract_max_gleaning=0, chunk_token_size=600, chunk_overlap_token_size=50)
    start = time.perf_counter()
    peak = 0
    report = {'size':size,'status':'running','lightrag_version':importlib.metadata.version('lightrag-hku')}
    try:
        await rag.initialize_storages()
        await initialize_pipeline_status()
        docs = [json.dumps({k:p.get(k) for k in ('parent_asin','categories','features','details')})[:2500] for p in products]
        task = asyncio.create_task(rag.ainsert(docs, ids=[p['parent_asin'] for p in products], file_paths=[p['parent_asin'] for p in products]))
        while not task.done():
            peak = max(peak, psutil.Process().memory_info().rss)
            if time.perf_counter() - start > seconds or peak > 8 * 2**30:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                report['status'] = 'infeasible_time_or_memory_gate'
                break
            await asyncio.sleep(1)
        if task.done() and not task.cancelled():
            await task
            report['ingestion_seconds'] = time.perf_counter() - start
            report['document_status_counts'] = await rag.doc_status.get_status_counts()
            states = [await rag.doc_status.get_by_id(p['parent_asin']) for p in products]
            processed = sum(s is not None and str(s.get('status', '')).lower().split('.')[-1] == 'processed' for s in states)
            report['catalog_documents_processed'] = processed
            if processed != size:
                raise RuntimeError(f'Insertion returned with only {processed}/{size} catalog documents processed')
            query = await rag.aquery_data('Find ' + str(products[0].get('categories',[])) + ' ' + str(products[0].get('features',[]))[:100], QueryParam(mode='mix', top_k=10, chunk_top_k=10, enable_rerank=False))
            write_json(folder / 'query_before_delete.json', query)
            deleted = products[0]['parent_asin']
            begin = time.perf_counter()
            deletion = await rag.adelete_by_doc_id(deleted)
            report['deletion_seconds'] = time.perf_counter() - begin
            report['deletion_result'] = str(deletion)
            report['deleted_document_absent'] = await rag.full_docs.get_by_id(deleted) is None
            begin = time.perf_counter()
            await rag.ainsert(docs[0], ids=deleted, file_paths=deleted)
            report['reinsert_seconds'] = time.perf_counter() - begin
            report['status'] = 'measured_pilot'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        report.update(elapsed_seconds=time.perf_counter()-start, peak_process_rss_mb=peak/2**20, model_calls=len(calls), model_usage=calls, manifest=manifest({'size':size,'seconds':seconds},[]))
        write_json(folder / 'results.json', report)
        await rag.finalize_storages()
    print({k:v for k,v in report.items() if k not in ('model_usage','manifest')}, flush=True)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--size',type=int,default=100)
    parser.add_argument('--seconds',type=int,default=1200)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.child:
        asyncio.run(run(args.size,args.seconds))
    else:
        from extension.watchdog import bounded_process
        result = bounded_process([sys.executable, '-m', 'extension.lightrag_benchmark', '--child', '--size', str(args.size), '--seconds', str(args.seconds)], args.seconds)
        folder = ARTIFACTS / 'updates' / f'lightrag-{args.size}'
        result['scope'] = 'Whole pilot including initialization, ingestion and follow-on checks; stricter than ingestion-only budget. Family RSS excludes external model server.'
        write_json(folder / 'watchdog.json', result)
        if result['gate'] or result['returncode']:
            write_json(folder / 'results.json', {'status':'infeasible_external_gate', 'size':args.size, **result, 'manifest':manifest(vars(args))})
