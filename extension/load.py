"""Scheduled response arrivals including client backlog, server queues and failures."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import ctypes
import json
import threading
import time
import urllib.request
import urllib.error
import psutil
from extension.common import ARTIFACTS,read_jsonl,write_json,write_jsonl,manifest,latency_summary


def request(url,operation,body):
    req=urllib.request.Request(url+'/'+operation,json.dumps(body).encode(),{'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=6) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
    except Exception as e:return 599,{'error':type(e).__name__}


def run(args):
    workload=read_jsonl(args.workload);records=[];samples=[];lock=threading.Lock();done=threading.Event();start=time.perf_counter();wall_start=time.time()
    if hasattr(ctypes,'windll'):ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    def monitor():
        tracked={}
        while not done.wait(1):
            rss=cpu=0
            for candidate in psutil.process_iter(['name','cmdline']):
                try:
                    cmd=candidate.info['cmdline'] or []
                    if 'extension.service' in cmd or ('spawn_main' in ' '.join(cmd) and any('techjam-26' in c for c in cmd)):
                        p=tracked.setdefault(candidate.pid,candidate);rss+=p.memory_info().rss;cpu+=p.cpu_percent()/100
                except psutil.Error:pass
            samples.append({'elapsed_s':time.perf_counter()-start,'wall_s':time.time(),'rss_bytes':rss,'cpu_cores':cpu,'available_ram_bytes':psutil.virtual_memory().available})
    threading.Thread(target=monitor,daemon=True).start()
    event_number=0;session_number=0;offered=[];generator_bound=False
    def play(number,first_event):
        session=workload[number%len(workload)];sid=f'{args.name}-{number}'
        reset_status,_=request(args.url,'reset',{'session_id':sid,'user_profile':session.get('profile',{})})
        for j,turn in enumerate(session['turns']):
            planned=start+(first_event+j)/args.rate
            delay=planned-time.perf_counter()
            if delay>0:time.sleep(delay)
            sent=time.perf_counter();status,response=request(args.url,'respond',{'session_id':sid,'request_id':f'{sid}-{j}',
                'turn':j+1,'top_k':10,'message':turn['message'],'timeout_seconds':2})
            completed=time.perf_counter();result=response.get('result',{});ids=[r['parent_asin'] for r in result.get('recommendations',[])]
            record={'session':number,'turn':j+1,'scheduled_s':planned-start,'sent_s':sent-start,'completed_s':completed-start,
                'latency_ms':(completed-planned)*1000,'client_lag_ms':max(0,(sent-planned)*1000),'status':status,'reset_status':reset_status,
                'queue_ms':response.get('queue_ms'),'service_ms':response.get('service_ms'),'ids':ids,
                'ranking_equal':status==200 and result.get('recommendations')==turn['expected'],'trace':response.get('route_trace')}
            with lock:records.append(record)
        request(args.url,'close',{'session_id':sid})
    try:
        with ThreadPoolExecutor(max_workers=args.users) as pool:
            while event_number<args.requests or event_number/args.rate<args.duration:
                scheduled=start+event_number/args.rate
                delay=scheduled-time.perf_counter()-.1
                if delay>0:time.sleep(delay)
                offered.append(pool.submit(play,session_number,event_number));event_number+=len(workload[session_number%len(workload)]['turns']);session_number+=1
                if len(offered)-sum(f.done() for f in offered)>2000:generator_bound=True;break
            for future in as_completed(offered):future.result()
    finally:
        done.set()
        if hasattr(ctypes,'windll'):ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    elapsed=time.perf_counter()-start;write_jsonl(ARTIFACTS/f'load/{args.name}-raw.jsonl',records);write_jsonl(ARTIFACTS/f'load/{args.name}-resources.jsonl',samples)
    gaps=[b['wall_s']-a['wall_s'] for a,b in zip(samples,samples[1:])];continuous=bool(samples) and max(gaps,default=0)<5 and abs((time.time()-wall_start)-elapsed)<3
    failures=sum(r['status']!=200 for r in records);latency=latency_summary([r['latency_ms'] for r in records])
    summary={'requests':len(records),'scheduled_response_rps':args.rate,'successful_rps':(len(records)-failures)/elapsed,'elapsed_seconds':elapsed,
        'latency':latency,'failure_rate':failures/max(1,len(records)),'ranking_mismatches':sum(not r['ranking_equal'] for r in records if r['status']==200),
        'queue':latency_summary([r['queue_ms'] for r in records if r['queue_ms'] is not None]),'service':latency_summary([r['service_ms'] for r in records if r['service_ms'] is not None]),
        'client_lag':latency_summary([r['client_lag_ms'] for r in records]),'generator_backlog_limit_hit':generator_bound,'resource_continuity_valid':continuous,
        'peak_service_rss_bytes':max((s['rss_bytes'] for s in samples),default=0),'gate_2s':continuous and not generator_bound and latency['p99_ms']<=2000 and failures/max(1,len(records))<=.01}
    write_json(ARTIFACTS/f'load/{args.name}.json',{'manifest':manifest({k:str(v) if hasattr(v,'resolve') else v for k,v in vars(args).items()},[args.workload]),'summary':summary});print(summary,flush=True)

if __name__=='__main__':
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('--workload',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:8092');p.add_argument('--rate',type=float,default=5)
    p.add_argument('--requests',type=int,default=10000);p.add_argument('--users',type=int,default=10);p.add_argument('--duration',type=float,default=0);p.add_argument('--name',default='screen');run(p.parse_args())
