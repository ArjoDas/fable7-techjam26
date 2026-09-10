"""Resumable local development screens. Sealed evaluation is a separate command."""
import subprocess
import sys
from extension.common import ARTIFACTS,write_json,manifest


def main():
    folder=ARTIFACTS/'quality';source=ARTIFACTS/'datasets/dev-screen-frozen.jsonl';results=[]
    commands=[['extension.learned','train'],['extension.residual','--limit','200']]
    for module,*args in commands:
        log=folder/(module.rsplit('.',1)[-1]+'-training.log');log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-u','-m',module,*args],stdout=stream,stderr=subprocess.STDOUT)
        if code:raise RuntimeError('Training failed: '+module)
    for variant in ('main','lexical','rules','hybrid','graph','tinybert','tinybert-100','tinybert-lexical','gated-tinybert','minilm-cross','learned','residual'):
        name=f'dev-{variant}-natural-interactive-screen-v2';path=folder/(name+'.json')
        if not path.exists():
            with (folder/(name+'.log')).open('w',encoding='utf-8') as stream:
                code=subprocess.call([sys.executable,'-u','-m','extension.evaluate','--variant',variant,'--input',str(source),'--label','screen-v2'],stdout=stream,stderr=subprocess.STDOUT)
        else:code=0
        results.append({'variant':variant,'returncode':code,'output':str(path)});write_json(folder/'screen-progress.json',results);print(results[-1],flush=True)
    write_json(folder/'screen-campaign.json',{'manifest':manifest({},[source]),'runs':results,'serving_latency_scope':'Accuracy screen with concurrent generation; not isolated tail evidence'})

if __name__=='__main__':main()
