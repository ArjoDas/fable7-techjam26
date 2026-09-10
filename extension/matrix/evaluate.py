"""Official simulator semantics with independently rendered customer wording."""
import argparse,json,time
from dataclasses import asdict
from collections import defaultdict
from evaluator import local_evaluator as official
from extension.matrix.common import *
from extension.matrix.events import decode,render
from extension.common import latency_summary

def evaluate(agent,samples,products,level='constrained',seed=SEEDS[0],replay=False,bank=None):
    results=[];active=set(products)
    for index,sample in enumerate(samples):
        target=sample['ground_truth']['parent_asin']
        if target not in active:continue
        sid='matrix-'+sample['sample_id'];agent.reset(sid,sample['user_profile']);disclosed=set();boundary=False;changed=sample['scenario_type']!='intent_override'
        card,behavior=official.materialize_hidden_fields(sample,products);effective={**sample,'intent_card':card,'behavior':behavior}
        original=official.initial_message(effective,official.coarse_category(products[target].get('categories',[])),disclosed);turns=[];hit=None;rank=None
        for turn in range(1,official.MAX_TURNS+1):
            event=decode(original);message,fallback=render(event,level,sample['sample_id'],seed,sample.get('split','dev'),bank);began=time.perf_counter();error=None
            try:response=agent.respond(sid,message,turn,official.TOP_K)
            except Exception as exc:response={'message':'','ask_attribute':None,'recommendations':[]};error=type(exc).__name__
            elapsed=(time.perf_counter()-began)*1000
            if not isinstance(response,dict) or not isinstance(response.get('message'),str):response={'message':'','ask_attribute':None,'recommendations':[]}
            ranked=official.normalize_recommendations(response.get('recommendations'),active);trace=getattr(agent,'trace',{}).get(sid,{})
            base=getattr(agent,'base',getattr(getattr(agent,'store',None),'agent',agent));pool=trace.get('candidate_ids',getattr(base,'_sessions',{}).get(sid,{}).get('last_candidates',[]))[:100]
            turns.append({'turn':turn,'canonical':original,'event':asdict(event),'message':message,'recommendations':ranked,'candidate_ids':pool,'ask_attribute':response.get('ask_attribute'),
                'latency_ms':elapsed,'trace':trace,'paraphrase_fallbacks':fallback,'error':error,'eligible':changed})
            if changed and target in ranked:hit=turn;rank=ranked.index(target)+1;break
            override=effective.get('behavior',{}).get('override') or {}
            if not changed and turn+1==int(override.get('turn',3)):
                changed=True;value=str(override.get('new_value',''))
                if value:disclosed.add(value)
                original=str(override.get('message','Actually, please ignore my earlier preference.'))
            else:original,boundary=official.customer_reply(effective,'other' if replay else response.get('ask_attribute'),disclosed,boundary)
        results.append({'sample_id':sample['sample_id'],'target':target,'group':sample.get('group','original'),'scenario_type':sample['scenario_type'],
            'category':str((products[target].get('categories') or ['unknown'])[0]),'hit':hit is not None,'first_hit_turn':hit,'best_rank':rank,'reciprocal_rank':0 if rank is None else 1/rank,'turns':turns})
        if hasattr(agent,'close'):agent.close(sid)
        else:agent._sessions.pop(sid,None)
        if (index+1)%50==0:print('Matrix evaluated',index+1,'/',len(samples),flush=True)
    return results

def summary(rows):
    output=official.metric_summary(rows);n=max(1,len(rows));mttc=output['mttc']
    output['experimental_technical_score']=None if mttc is None else .5*output['hit_rate_at_10']+.3*output['mrr']+.2*max(0,min(1,(11-mttc)/10))
    output['hit10_by_turn5']=sum(r['hit'] and r['first_hit_turn']<=5 for r in rows)/n
    output['recall100_by_turn5']=sum(any(t['eligible'] and t['turn']<=5 and r['target'] in t['candidate_ids'] for t in r['turns']) for r in rows)/n
    turns=[t for r in rows for t in r['turns']];output['latency']=latency_summary([t['latency_ms'] for t in turns]);output['errors']=sum(t['error'] is not None for t in turns)
    converted=[t for t in turns if t['trace'].get('event')]
    output['conversion_attempts']=sum('canonical_text' in t['trace'] for t in turns);output['conversion_successes']=len(converted)
    output['event_kind_correct']=sum(t['trace']['event']['kind']==t['event']['kind'] for t in converted)
    def normalized(v):return str(v).casefold().strip(' .;,')
    output['value_sequence_correct']=sum(list(map(normalized,t['trace']['event']['values']))==list(map(normalized,t['event']['values'])) for t in converted)
    output['unsupported_normalizations']=sum(any(normalized(v) not in set(map(normalized,t['event']['values'])) for v in t['trace']['event']['values']) for t in converted)
    output['paraphrase_literal_fallback_turns']=sum(bool(t['paraphrase_fallbacks']) for t in turns)
    return output

def main(args):
    from extension.matrix.growth import OrderedCatalog
    from extension.matrix.translate import TranslatedAgent
    from extension.factory import create
    run_manifest=manifest(vars(args),[HOME/f'prepared/{args.split}.jsonl',HOME/f'snapshots/{args.schedule}-{args.size}.jsonl'])
    rows=read_jsonl(HOME/f'prepared/{args.split}.jsonl')
    if args.split=='test':
        if not (HOME/'selection.json').exists():raise RuntimeError('Matrix finalists must be frozen before sealed evaluation')
        from pathlib import Path
        frozen=json.loads((HOME/'selection.json').read_text(encoding='utf-8'))['manifest'];current=manifest({})
        if current['source_hashes']!=frozen['source_hashes'] or current['artifact_provenance_hashes']!=frozen['artifact_provenance_hashes']:raise RuntimeError('Code/model artifacts changed after matrix selection')
        if any(sha256(Path(p))!=value for p,value in frozen['inputs'].items()):raise RuntimeError('Frozen matrix input changed')
    store=OrderedCatalog(HOME/f'published/{args.schedule}-{args.size}')
    if len(store.products)!=args.size:raise RuntimeError('Requested checkpoint is not the currently published catalog')
    rows=[r for r in rows if r['ground_truth']['parent_asin'] in store.products];rows=sorted(rows,key=lambda r:stable(r['sample_id']))
    if args.limit:rows=rows[:args.limit]
    vectors=None
    if args.variant=='semantic':agent=create(store,'rag-passages-corrected');vectors=agent.vectors
    elif args.variant in ('rules','qwen'):
        if args.variant=='qwen':
            from extension.passages import PassageIndex
            vectors=PassageIndex(store)
        agent=TranslatedAgent(store,args.variant,vectors,args.threshold)
    else:agent=store.agent
    bank_path=HOME/'paraphrases/bank.json';bank=json.loads(bank_path.read_text(encoding='utf-8')) if bank_path.exists() else {}
    if args.level=='semantic' and not bank:raise RuntimeError('Generate retained semantic alternatives before evaluation')
    name=f'{args.schedule}-{args.size}-{args.variant}-{args.level}-{args.split}-s{args.seed}-{args.label}'+('-replay' if args.replay else '')
    path=HOME/f'quality/{name}.json'
    if path.exists():raise RuntimeError('Result already retained; use another label')
    try:results=evaluate(agent,rows,store.products,args.level,args.seed,args.replay,bank)
    finally:
        if vectors:vectors.close()
        store.close()
    groups=defaultdict(list);cohorts=defaultdict(list);scenarios=defaultdict(list);categories=defaultdict(list)
    sizes=SCHEDULES[args.schedule];position=sizes.index(args.size);membership=json.loads((HOME/'prepared/membership.json').read_text(encoding='utf-8'))
    previous=set(membership[args.schedule][str(sizes[max(0,position-1)])])
    for r in results:
        groups['original' if r['group']=='original' else 'new'].append(r);cohorts['persistent' if r['target'] in previous else 'newly_introduced'].append(r)
        scenarios[r['scenario_type']].append(r);categories[r['category']].append(r)
    write_json(path,{'manifest':run_manifest,
        'aggregate':summary(results),'by_group':{k:summary(v) for k,v in groups.items()},'by_cohort':{k:summary(v) for k,v in cohorts.items()},'by_scenario':{k:summary(v) for k,v in scenarios.items()},'by_category':{k:summary(v) for k,v in categories.items()},'sessions':results})
    print(name,summary(results),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--schedule',choices=SCHEDULES,default='frozen');p.add_argument('--size',type=int,default=50000)
    p.add_argument('--variant',choices=['main','rules','qwen','semantic'],default='main');p.add_argument('--level',choices=['constrained','wording','semantic'],default='constrained')
    p.add_argument('--split',choices=['train','dev','test'],default='dev');p.add_argument('--seed',type=int,default=SEEDS[0]);p.add_argument('--limit',type=int)
    p.add_argument('--label',default='screen');p.add_argument('--threshold',type=float,default=.65);p.add_argument('--replay',action='store_true');main(p.parse_args())
