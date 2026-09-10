"""Small budgeted provider screens using real retrieval shortlists, never injected targets."""
import argparse
from collections import Counter
import time
from extension.common import ARTIFACTS,read_jsonl,write_json,write_jsonl,manifest,latency_summary
from extension.evaluate import build
from extension.datasets import Shopper
from extension.providers import Matcher,Ledger


def run(limit,timeout,stage):
    dataset=ARTIFACTS/'datasets/dev.jsonl';rows=sorted(read_jsonl(dataset),key=lambda r:r['sample_id'])[:limit]
    folder=ARTIFACTS/'api';cases_path=folder/f'cases-{limit}.jsonl'
    if cases_path.exists():cases=read_jsonl(cases_path)
    else:
        store,agent=build('hybrid');cases=[]
        for row in rows:
            sid=row['sample_id'];agent.reset(sid,{});shopper=Shopper(row);messages=[]
            for turn in range(1,4):
                text=shopper.message(turn,'other');messages.append(text);agent.respond(sid,text,turn,10)
            ids=agent.trace[sid]['candidate_ids'][:20]
            cards=[{'ref':str(i),'category':agent.base._product_views[a][1],'evidence':' '.join(agent.base._product_views[a][:6])[:450]} for i,a in enumerate(ids)]
            cases.append({'sample_id':sid,'query':' '.join(messages),'cards':cards,'ids':ids,'target':row['target']});agent.close(sid)
        store.close();write_jsonl(cases_path,cases)
    ledger=Ledger();outcomes=[]
    for provider in ('openai-nano','openai-luna','gemini-lite'):
        for mode in ('ranking','extraction'):
            matcher=Matcher(provider,stage,mode,ledger)
            for case in cases:
                began=time.perf_counter();result={};usage={};error=None
                try:result,usage=matcher.match(case['query'],case['cards'],timeout)
                except Exception as exc:error=type(exc).__name__+str(getattr(exc,'code',''))
                ids=case['ids'];refs=result.get('ranking',[])
                ranked=[ids[int(i)] for i in refs if str(i).isdigit() and int(i)<len(ids)] if isinstance(refs,list) else []
                ranked=list(dict.fromkeys(ranked+ids))
                outcomes.append({'sample_id':case['sample_id'],'provider':provider,'mode':mode,'timeout_seconds':timeout,
                    'elapsed_ms':(time.perf_counter()-began)*1000,'response':result,'usage':usage,'error':error,
                    'shortlist_target_present':case['target'] in ids,'baseline_hit10':case['target'] in ids[:10],
                    'reranked_hit10':case['target'] in ranked[:10] if mode=='ranking' else None})
                write_jsonl(folder/f'screen-{stage}-{timeout}-raw.jsonl',outcomes)
                if error and (error.startswith('HTTPError40') or error=='BudgetExceeded'):break
            print(provider,mode,'completed; ledger',ledger.summary(),flush=True)
    summary=[]
    for provider in ('openai-nano','openai-luna','gemini-lite'):
        for mode in ('ranking','extraction'):
            part=[r for r in outcomes if r['provider']==provider and r['mode']==mode]
            summary.append({'provider':provider,'mode':mode,'calls':len(part),'errors':dict(Counter(r['error'] for r in part if r['error'])),
                'latency':latency_summary([r['elapsed_ms'] for r in part]),'baseline_hits':sum(r['baseline_hit10'] for r in part),
                'reranked_hits':sum(bool(r['reranked_hit10']) for r in part),'extraction_quality_requires_downstream_retrieval':mode=='extraction'})
    write_json(folder/f'screen-{stage}-{timeout}.json',{'manifest':manifest({'limit':limit,'timeout':timeout,'stage':stage},[cases_path]),'summary':summary,'budget':ledger.summary(),'tail_claim':'Exploratory only, not production p99 evidence'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=24);p.add_argument('--timeout',type=float,default=15);p.add_argument('--stage',default='screen');a=p.parse_args();run(a.limit,a.timeout,a.stage)
