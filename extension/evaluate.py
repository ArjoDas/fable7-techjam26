from extension.common import dataset_path
"""Evaluate frozen paired tasks; keep official metrics separate from this benchmark."""
import argparse
from collections import defaultdict
import json
import time
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest,latency_summary
from extension.datasets import Shopper


def build(variant,catalog=None):
    from extension.catalog import Catalog
    from extension.factory import create
    store=Catalog(ARTIFACTS/'stores/evaluation',catalog or ARTIFACTS/'catalog/catalog-60000.jsonl')
    return store,create(store,variant)



def evaluate(agent,rows,protocol=False,replay=False,progress_path=None):
    results=[]
    for index,row in enumerate(rows):
        sid=row['sample_id'];agent.reset(sid,{});shopper=Shopper(row,protocol,replay);asked=None;hit=0;rr=0;recall=False;transcript=[]
        for turn in range(1,6):
            message=shopper.message(turn,asked);started=time.perf_counter()
            result=agent.respond(sid,message,turn,10);elapsed=(time.perf_counter()-started)*1000
            recommendations=[r['parent_asin'] for r in result['recommendations']]
            trace=getattr(agent,'trace',{}).get(sid,{})
            pool=trace.get('candidate_ids',[])
            if not pool and hasattr(agent,'_sessions'):
                # Actual main retrieval pool for diagnostics, never used to change its output.
                state=agent._sessions[sid];pool=state.get('last_candidates',[])
            recall=recall or row['target'] in pool
            base=getattr(agent,'base',agent)
            categories={base._product_views[a][1] for a in recommendations if a in base._product_views}
            popularity=[base._popularity.get(a,0) for a in recommendations]
            exposure={'returned':len(recommendations),'distinct_category_texts':len(categories),
                'low_popularity_fraction':sum(v<=10 for v in popularity)/max(1,len(popularity)),
                'category_compatible_fraction':sum(a in getattr(agent,'aliases',{}).get(trace.get('category_alias'),set()) for a in recommendations)/max(1,len(recommendations)) if trace.get('category_alias') else None,
                'active_constraint_satisfaction':sum(agent._allowed(a,trace.get('constraints',[])) for a in recommendations)/max(1,len(recommendations)) if hasattr(agent,'_allowed') else None}
            transcript.append({'turn':turn,'message':message,'response':result,'latency_ms':elapsed,'trace':trace,'browsing_exposure':exposure})
            eligible=turn>=3 if row['scenario'] in ('partial_override','category_override','browsing_to_buying') else True
            if eligible and row['target'] in recommendations:
                hit=turn;rr=1/(recommendations.index(row['target'])+1);break
            asked=result.get('ask_attribute')
        results.append({'sample_id':sid,'target':row['target'],'group':row['group'],'scenario':row['scenario'],
                        'category':row['category_path'][0],'style':row['style'],'hit':bool(hit),'turn_to_hit':hit or 6,'rr':rr,'recall100':recall,'transcript':transcript})
        if progress_path is not None:
            progress_path.parent.mkdir(parents=True,exist_ok=True)
            with progress_path.with_suffix('.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
            if (index+1)%10==0:write_json(progress_path,{'completed':index+1,'total':len(rows),'hits':sum(r['hit'] for r in results),'model_calls':getattr(agent,'model_calls',0)})
        if hasattr(agent,'close'):agent.close(sid)
        else:agent._sessions.pop(sid,None)
        if (index+1)%50==0:print('evaluated',index+1,'/',len(rows),flush=True)
    return results


def aggregate(rows):
    n=len(rows)
    return {'tasks':n,'hit_rate_at_10':sum(r['hit'] for r in rows)/max(1,n),'mrr':sum(r['rr'] for r in rows)/max(1,n),
            'turns_capped_at_6':sum(r['turn_to_hit'] for r in rows)/max(1,n),'recall100_any_turn':sum(r['recall100'] for r in rows)/max(1,n),
            'clarifications_per_task':sum(bool(t['response'].get('ask_attribute')) and not t['response']['recommendations'] for r in rows for t in r['transcript'])/max(1,n),
            'response_latency':latency_summary([t['latency_ms'] for r in rows for t in r['transcript']])}


def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',default='rules');p.add_argument('--split',default='dev');p.add_argument('--limit',type=int)
    p.add_argument('--input',type=__import__('pathlib').Path);p.add_argument('--protocol',action='store_true');p.add_argument('--replay',action='store_true');p.add_argument('--label',default='');args=p.parse_args()
    dataset=args.input or dataset_path(args.split);rows=sorted(read_jsonl(dataset),key=lambda r:r['sample_id'])
    if args.split=='test' and not (ARTIFACTS/'selection/frozen.json').exists():raise RuntimeError('Freeze finalists before opening sealed test')
    rows=rows[:args.limit] if args.limit else rows
    from extension.common import write_jsonl
    frozen_input=ARTIFACTS/f'quality/inputs/{args.split}-{args.variant}-{args.label or "full"}.jsonl'
    write_jsonl(frozen_input,rows)
    store,agent=build(args.variant);start=time.perf_counter()
    progress_path=ARTIFACTS/f'quality/progress/{args.variant}-{args.label}-{time.time_ns()}.json'
    try:results=evaluate(agent,rows,args.protocol,args.replay,progress_path)
    finally:store.close()
    name='-'.join(filter(None,[args.split,args.variant,'protocol' if args.protocol else 'natural','replay' if args.replay else 'interactive',args.label]))
    groups=defaultdict(list);scenarios=defaultdict(list);categories=defaultdict(list)
    ambiguity_path=ARTIFACTS/'datasets/ambiguity.json'
    ambiguity={r['sample_id']:r for r in json.loads(ambiguity_path.read_text(encoding='utf-8'))['rows']} if ambiguity_path.exists() else {}
    for row in results:
        groups['original' if row['group']=='original' else 'new'].append(row)
        scenarios[row['scenario']].append(row);categories[row['category']].append(row)
    summary={'manifest':manifest({k:str(v) if hasattr(v,'resolve') else v for k,v in vars(args).items()},[frozen_input]),'elapsed_seconds':time.perf_counter()-start,'aggregate':aggregate(results),
             'by_group':{k:aggregate(v) for k,v in groups.items()},'by_scenario':{k:aggregate(v) for k,v in scenarios.items()},'by_category':{k:aggregate(v) for k,v in categories.items()},
             'source_identifiable_by_group':{k:aggregate([r for r in v if ambiguity.get(r['sample_id'],{}).get('identifiable_from_full_evidence')]) for k,v in groups.items()},'sessions':results}
    write_json(ARTIFACTS/f'quality/{name}.json',summary);print(name,summary['aggregate'],flush=True)

if __name__=='__main__':main()
