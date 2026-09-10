"""Official evaluator regression for the extension wrapper, without model dependencies."""
import argparse
import time
from extension.common import ARTIFACTS, ROOT, manifest, read_jsonl, write_json
from extension.agent import Agent
from evaluator.local_evaluator import evaluate,catalog_index


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--historical',action='store_true');args=parser.parse_args()
    start=time.perf_counter();agent=Agent(ROOT/'data/catalog.jsonl')
    ids,categories,products=catalog_index(ROOT/'data/catalog.jsonl')
    paths={'public':ROOT/'data/public_set.jsonl'}
    if args.historical:
        for p in (ROOT/'data/releases/cp7/datasets').glob('*.jsonl'):
            if 'cards' not in p.name:paths[p.stem]=p
    for name,path in paths.items():
        result=evaluate(agent,read_jsonl(path),ids,categories,products)
        write_json(ARTIFACTS/f'baselines/{name}.json',{'manifest':manifest({'variant':'extension-protocol'},[path,ROOT/'data/catalog.jsonl']),
            'aggregate':{k:v for k,v in result.items() if k!='sessions'},'sessions':result['sessions'],
            'model_calls':agent.model_calls,'elapsed_seconds':time.perf_counter()-start,
            'nonprotocol_final_traces':sum(t['route']!='protocol' for t in agent.trace.values())})
        print(name,{k:v for k,v in result.items() if k not in ('sessions','scenario_metrics')},'model calls',agent.model_calls,flush=True)
        if name=='public':
            assert (result['hit_rate_at_10'],result['mrr'],result['mttc'],result['recommended_technical_score'])==(1.,1.,2.1,.978)
            assert agent.model_calls==0


if __name__=='__main__':main()
