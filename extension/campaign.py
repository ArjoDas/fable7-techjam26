"""Run the full frozen-data campaign after generation/audit, with stage checkpoints."""
import argparse
import json
import subprocess
import sys
import time
from extension.common import ARTIFACTS,write_json,manifest


def command(module,*args):
    label=module.rsplit('.',1)[-1]+'-'+'-'.join(str(a).replace('/','_').replace(':','') for a in args)
    folder=ARTIFACTS/'campaign';folder.mkdir(parents=True,exist_ok=True)
    with (folder/(label+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,'-u','-m',module,*map(str,args)],stdout=log,stderr=subprocess.STDOUT)
    write_json(folder/'current.json',{'manifest':manifest({'module':module,'args':args}),'returncode':result.returncode,'log':str(folder/(label+'.log'))})
    if result.returncode:raise RuntimeError('Stage failed: '+module+'; see retained log')
    print('Completed',module,*args,flush=True)


def main():
    while not (ARTIFACTS/'datasets/semantic-audit.json').exists():time.sleep(2)
    command('extension.learned','train');command('extension.learned','score');command('extension.residual','--limit',400)
    variants=('main','rules','hybrid','graph','tinybert','tinybert-100','tinybert-lexical','gated-tinybert','minilm-cross','learned','residual','rag','rag-passages')
    for variant in variants:
        path=ARTIFACTS/f'quality/dev-{variant}-natural-interactive-canonical-dev.json'
        if not path.exists():command('extension.evaluate','--variant',variant,'--split','dev','--label','canonical-dev')
    # Local generative route is measured only after generation has stopped.
    command('extension.evaluate','--variant','local','--split','dev','--limit',100,'--label','local-deadline-screen')
    command('extension.selection','freeze');command('extension.selection','confirm')
    selection=json.loads((ARTIFACTS/'selection/frozen.json').read_text(encoding='utf-8'));candidate=selection['local_finalists'][0]
    command('extension.diagnostics','--variant',candidate)
    command('extension.load_campaign','--variant',candidate,'--confirm')
    command('extension.outcomes');command('extension.report')

if __name__=='__main__':main()
