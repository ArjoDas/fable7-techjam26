"""Retain fixed natural/protocol load traces and expected output for a serving variant."""
import argparse
from extension.common import ARTIFACTS,read_jsonl,write_jsonl,write_json,manifest,dataset_path
from extension.evaluate import build
from extension.datasets import Shopper


def main(variant,limit):
    store,agent=build(variant);rows=sorted(read_jsonl(dataset_path('dev')),key=lambda r:r['sample_id'])[:limit];workload=[]
    for row in rows:
        for protocol in (False,True):
            sid=row['sample_id']+str(protocol);agent.reset(sid,{});shopper=Shopper(row,protocol=protocol,replay=True);turns=[]
            for turn in range(1,6):
                message=shopper.message(turn,'other');response=agent.respond(sid,message,turn,10)
                turns.append({'message':message,'expected':response['recommendations']})
            workload.append({'sample_id':row['sample_id'],'profile':{},'target':row['target'],'family':'protocol' if protocol else 'natural','turns':turns});agent.close(sid)
    store.close();path=ARTIFACTS/f'load/workload-{variant}.jsonl';write_jsonl(path,workload)
    write_json(path.with_suffix('.manifest.json'),manifest({'variant':variant,'limit':limit},[dataset_path('dev'),path]));print('Workload ready',len(workload),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--variant',default='tinybert-lexical');p.add_argument('--limit',type=int,default=50);a=p.parse_args();main(a.variant,a.limit)
