"""Isolated local serving screens and 30,000-request/30-minute confirmation."""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import psutil
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest


def stop(process):
    try:
        parent=psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try:child.terminate()
            except psutil.Error:pass
        parent.terminate();process.wait(timeout=10)
    except (psutil.Error,subprocess.TimeoutExpired):
        try:process.kill()
        except OSError:pass


def assert_idle():
    for p in psutil.process_iter(['cmdline']):
        cmd=p.info['cmdline'] or []
        if any(module in cmd for module in ('extension.datasets','extension.generation_campaign','extension.semantic_audit','extension.quality_campaign','extension.representation_benchmark','extension.lightrag_benchmark')):
            raise RuntimeError('Stop generation, quality and preprocessing before isolated load: '+str(p.pid))


def server(workers,variant):
    folder=ARTIFACTS/'load';folder.mkdir(parents=True,exist_ok=True);log=(folder/f'server-{workers}-{variant}.log').open('a',encoding='utf-8')
    process=subprocess.Popen([sys.executable,'-u','-m','extension.service','--workers',str(workers),'--variant',variant],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        if process.poll() is not None:log.close();raise RuntimeError('Server startup failed')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8092',timeout=2) as response:
                if json.load(response)['ready']:return process,log
        except Exception:pass
        time.sleep(1)
    stop(process);log.close();raise RuntimeError('Readiness timeout')


def measurement(workers,users,rate,requests,duration,name,variant):
    subprocess.run([sys.executable,'-u','-m','extension.load','--workload',str(ARTIFACTS/f'load/workload-{variant}.jsonl'),
        '--users',str(users),'--rate',str(rate),'--requests',str(requests),'--duration',str(duration),'--name',name],check=True)
    return json.loads((ARTIFACTS/f'load/{name}.json').read_text(encoding='utf-8'))['summary']


def run(variant,confirm):
    assert_idle();folder=ARTIFACTS/'load';screens=[]
    subprocess.run([sys.executable,'-m','extension.prepare_load','--variant',variant,'--limit','50'],check=True)
    for workers in (1,4,8):
        available=psutil.virtual_memory().available
        if available<workers*1.8*2**30:
            screens.append({'workers':workers,'outcome':'infeasible','reason':'Conservative measured-process memory budget','available_bytes':available});continue
        process,log=server(workers,variant)
        try:
            for users in (1,5,10):
                name=f'screen-{variant}-w{workers}-u{users}'
                result=measurement(workers,users,5,300,0,name,variant);screens.append({'workers':workers,'users':users,'summary':result})
                write_json(folder/'screen-matrix.json',screens)
        finally:stop(process);log.close()
    successful=[s for s in screens if s.get('summary',{}).get('gate_2s')]
    candidates=successful or [s for s in screens if 'summary' in s]
    if not candidates:raise RuntimeError('No serving configuration completed')
    best=min(candidates,key=lambda s:(s['summary']['failure_rate'],s['summary']['latency']['p99_ms'],s['workers']))
    write_json(folder/'selected-serving.json',{'manifest':manifest({'variant':variant}),'selection':best,'screen_gate_passed':bool(successful)})
    if not confirm:return
    process,log=server(best['workers'],variant);runs=[]
    try:
        for repetition in range(1,4):runs.append(measurement(best['workers'],best['users'],5,10000,0,f'confirmation-{variant}-{repetition}',variant))
        runs.append(measurement(best['workers'],best['users'],5,9000,1800,f'soak-{variant}',variant))
        saturation=[]
        for rate in (10,20,40):saturation.append(measurement(best['workers'],10,rate,1000,0,f'saturation-{variant}-{rate}',variant))
    finally:stop(process);log.close()
    write_json(folder/'final-confirmation.json',{'manifest':manifest({'variant':variant,'workers':best['workers'],'users':best['users']}),'runs':runs,'saturation':saturation,
        'passed':all(r['gate_2s'] and r['ranking_mismatches']==0 for r in runs),'qualification':'Local CPU hosting only; no cloud extrapolation presented as observation'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--variant',default='tinybert-lexical');p.add_argument('--confirm',action='store_true');a=p.parse_args();run(a.variant,a.confirm)
