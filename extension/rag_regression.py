"""Official regression with the semantic route and local parser configured."""
import argparse
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest
from extension.catalog import Catalog
from extension.factory import create
from evaluator.local_evaluator import evaluate,catalog_index


def main(variant='rag-local'):
    path=ROOT/'data/catalog.jsonl';store=Catalog(ARTIFACTS/'stores/official-rag',path);agent=create(store,variant);ids,categories,products=catalog_index(path)
    result=evaluate(agent,read_jsonl(ROOT/'data/public_set.jsonl'),ids,categories,products)
    report={'manifest':manifest({'variant':variant,'catalog':'official50k'},[path,ROOT/'data/public_set.jsonl']),
        'aggregate':{k:v for k,v in result.items() if k!='sessions'},'model_calls':agent.model_calls,'nonprotocol_final_traces':sum(t['route']!='protocol' for t in agent.trace.values())}
    write_json(ARTIFACTS/f'baselines/public-{variant}.json',report)
    assert (result['hit_rate_at_10'],result['mrr'],result['mttc'],result['recommended_technical_score'])==(1.,1.,2.1,.978)
    assert agent.model_calls==0 and report['nonprotocol_final_traces']==0
    print(report['aggregate'],'model calls',agent.model_calls,flush=True)
    if agent.vectors is not None:agent.vectors.close()
    store.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--variant',default='rag-local');args=parser.parse_args();main(args.variant)
