"""Finish passage preprocessing, compare RAG ablations, then resume retained campaign."""
import json
import subprocess
import sys
import time
from extension.common import ARTIFACTS,write_json,manifest


def run(module,*args):
    folder=ARTIFACTS/'rag';folder.mkdir(parents=True,exist_ok=True);name=module.rsplit('.',1)[-1]+'-'+'-'.join(args)
    with (folder/(name+'.log')).open('w',encoding='utf-8') as stream:
        code=subprocess.call([sys.executable,'-u','-m',module,*args],stdout=stream,stderr=subprocess.STDOUT)
    if code:raise RuntimeError('RAG stage failed: '+name)
    print('Completed',name,flush=True)


def main():
    path=ARTIFACTS/'vectors/passages/manifest.json';deadline=time.monotonic()+7200
    while not path.exists():
        if time.monotonic()>deadline:raise RuntimeError('Passage preprocessing did not finish within two hours')
        time.sleep(2)
    if json.loads(path.read_text(encoding='utf-8'))['products']!=60000:raise RuntimeError('Passage index is not full-catalog')
    if not (ARTIFACTS/'rag/unseen-update/result.json').exists():run('extension.passage_update_probe')
    source=str(ARTIFACTS/'datasets/dev-screen-frozen.jsonl')
    for variant in ('tinybert-lexical','rag','rag-passages','rag-local','rag-passages-local'):
        label='semantic-screen'
        folder=ARTIFACTS/'rag';folder.mkdir(parents=True,exist_ok=True)
        with (folder/(variant+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-u','-m','extension.evaluate','--variant',variant,'--input',source,'--limit','120','--label',label],stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Semantic screen failed: '+variant)
        print('Completed semantic screen',variant,flush=True)
    write_json(ARTIFACTS/'rag/screen-complete.json',{'manifest':manifest({}),'variants':['tinybert-lexical','rag','rag-passages','rag-local','rag-passages-local']})
    run('extension.generation_campaign')
    run('extension.campaign')

if __name__=='__main__':main()
