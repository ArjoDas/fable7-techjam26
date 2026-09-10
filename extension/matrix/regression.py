"""Unmodified official evaluator verifies each constrained compatibility path."""
from unittest.mock import patch
from evaluator.local_evaluator import evaluate,catalog_index
from extension.matrix.common import *
from extension.matrix.growth import OrderedCatalog
from extension.matrix.translate import TranslatedAgent

def main():
    store=OrderedCatalog(HOME/'catalogs/frozen');path=ROOT/'data/catalog.jsonl';ids,categories,products=catalog_index(path);results=[]
    try:
        for variant in ('main','rules','qwen'):
            agent=store.agent if variant=='main' else TranslatedAgent(store,variant)
            with patch('extension.models.LocalLLM.complete',side_effect=AssertionError('Protocol must bypass models')):
                result=evaluate(agent,read_jsonl(ROOT/'data/public_set.jsonl'),ids,categories,products)
            observed=tuple(result[k] for k in ('hit_rate_at_10','mrr','mttc','recommended_technical_score'))
            record={'variant':variant,'metrics':{k:v for k,v in result.items() if k!='sessions'},'model_calls':getattr(agent,'model_calls',0),'passed':observed==(1.,1.,2.1,.978) and getattr(agent,'model_calls',0)==0};results.append(record)
            write_json(HOME/'official-regression.json',{'manifest':manifest({},[path,ROOT/'data/public_set.jsonl']),'results':results})
            if not record['passed']:raise RuntimeError('Official compatibility failed: '+variant)
            print('Official compatibility',variant,observed,flush=True)
    finally:store.close()

if __name__=='__main__':main()
