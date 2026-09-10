"""Fresh Amazon-grounded paired tasks with frozen attribute-answer banks."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import hashlib
from pathlib import Path
import random
import re
from extension.common import ARTIFACTS,ROOT,manifest,read_jsonl,write_json,write_jsonl
from evaluator.local_evaluator import classify_constraint,coarse_category,intent_card

SEED=20260910
SCENARIOS=('buying','browsing','partial_override','category_override','browsing_to_buying','negation')


def evidence(p):
    values=[];title=str(p.get('title') or '').lower()
    for field in ('features','details'):
        raw=p.get(field) or ([] if field=='features' else {})
        items=[(str(k),str(v)) for k,v in raw.items()] if isinstance(raw,dict) else [(str(i),str(v)) for i,v in enumerate(raw)]
        for key,value in items:
            value=re.sub(r'\s+',' ',value).strip()
            if not 4<=len(value)<=200 or value.lower()==title:continue
            if field=='details' and key.lower() not in ('color','material','brand','style','size','department','compatible devices','connectivity technology','capacity','power source'):continue
            claim=f'{key}: {value}' if field=='details' else value
            values.append({'attribute':classify_constraint(claim),'value':claim,'source':f'{field}.{key}'})
    return values


def prepare():
    folder=ARTIFACTS/'datasets'
    if (folder/'manifest.json').exists():return
    products=read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl');original={p['parent_asin'] for p in products[:50000]}
    excluded=set()
    paths=[ROOT/'data/public_set.jsonl',*list((ROOT/'data/releases').glob('cp*/**/*.jsonl')),*list((ROOT/'data/releases/real-world-v1/datasets').glob('*.jsonl'))]
    for path in paths:
        for row in read_jsonl(path):
            target=(row.get('ground_truth') or {}).get('parent_asin')
            if target:excluded.add(target)
    sources={r['product']['parent_asin']:r['source_category'] for r in read_jsonl(ARTIFACTS/'catalog/additions.jsonl')}
    pools={k:[] for k in ('original','Clothing_Shoes_and_Jewelry','Electronics','Home_and_Kitchen')}
    for p in products:
        if p['parent_asin'] in excluded or len(evidence(p))<3:continue
        group='original' if p['parent_asin'] in original else sources[p['parent_asin']]
        pools[group].append(p)
    rng=random.Random(SEED)
    for pool in pools.values():rng.shuffle(pool)
    allocations={'train':[800,400,200,200],'dev':[400,200,100,100],'test':[400,200,100,100]}
    for split,counts in allocations.items():
        selected=[]
        for group,count in zip(pools,counts):
            if len(pools[group])<count:raise RuntimeError('Insufficient fresh supported targets: '+group)
            selected.extend((group,pools[group].pop()) for _ in range(count))
        rng.shuffle(selected);rows=[]
        for i,(group,p) in enumerate(selected):
            facts=evidence(p);rng.shuffle(facts);facts=facts[:5]
            scenario=SCENARIOS[i%6]
            old=products[(i*113+19)%len(products)]
            for attempt in range(100):
                if old.get('categories')!=p.get('categories') and evidence(old):break
                old=products[(i*113+20+attempt)%len(products)]
            rows.append({'sample_id':f'ext1_{split}_{i:04}','split':split,'group':group,'target':p['parent_asin'],
                'category_path':p.get('categories') or [p.get('main_category','product')],
                'coarse_category':coarse_category(p.get('categories') or []),'facts':facts,'scenario':scenario,
                'protocol_card':intent_card(p),'old_product':{'parent_asin':old['parent_asin'],'category_path':old.get('categories') or [],'facts':evidence(old)[:2]},
                'style':('fragmented','indirect','polite_meandering')[i%3] if split=='test' else ('informal','concise','comparison','typos')[i%4],
                'popularity':p.get('rating_number',0)})
        write_jsonl(folder/f'{split}-cards.jsonl',rows)
    write_json(folder/'manifest.json',{'manifest':manifest({'seed':SEED,'allocations':allocations},[ARTIFACTS/'catalog/catalog-60000.jsonl']),
        'targets':3200,'paired_transcripts':6400,'historical_targets_excluded':len(excluded),
        'answerability_rule':'At least three nonempty bounded source facts; ambiguity is measured separately, not excluded by retrieval success',
        'generation_rule':'Local Qwen paraphrases category-grounded facts and openings before evaluation; no live model simulator and no title reveal'})


def generate_one(row):
    from extension.models import LocalLLM
    card={'category_path':row['category_path'],'facts':[f['value'] for f in row['facts']]}
    prompt=('You are the CUSTOMER asking a shop assistant for help, never a seller or advertiser. Write in first person. '
        'Create natural shopping language from the supplied evidence. The product type must follow the complete category path. '
        'Do not invent properties, turn product names into different product types, copy any product title, or treat care instructions as product types. '
        'Return JSON {"opening":"I need ...", "answers":["I prefer ...", "It should ..."]}. The opening requests the category plus only the first fact. '
        'The answers array must contain exactly one natural customer paraphrase for EACH supplied fact, in the same order. '
        'Preserve numbers, negations, and factual meaning. Do not add prices or guarantees. Style: '+row['style']+'. Evidence: '+json.dumps(card,ensure_ascii=False))
    schema={'type':'object','properties':{'opening':{'type':'string'},'answers':{'type':'array','items':{'type':'string'},'minItems':len(row['facts']),'maxItems':len(row['facts'])}},'required':['opening','answers'],'additionalProperties':False}
    raw='';usage={}
    generation_config={'seed':SEED+int(hashlib.sha256(row['sample_id'].encode()).hexdigest()[:7],16),'max_tokens':800,'stop':['</think>','</s>'],'schema_version':2}
    try:
        raw,usage=LocalLLM(timeout=90).complete(prompt,max_tokens=800,seed=generation_config['seed'],schema=schema,stop=generation_config['stop'])
        parsed=json.loads(raw[raw.find('{'):raw.rfind('}')+1])
        if not isinstance(parsed.get('opening'),str) or not isinstance(parsed.get('answers'),list) or len(parsed['answers'])!=len(row['facts']) or not all(isinstance(a,str) and len(a)>3 for a in parsed['answers']):raise ValueError('Invalid answer bank')
        return {**row,'opening':parsed['opening'],'answers':parsed['answers'],'generation_config':generation_config,'generation_prompt':prompt,'generation_raw':raw,'generation_usage':usage,'generator':'Qwen3-4B-Q4_K_M'}
    except Exception as exc:
        return {**row,'opening':'I need '+str(row['category_path'][-1])+'. '+row['facts'][0]['value'],
                'answers':[f['value'] for f in row['facts']],'generation_config':generation_config,'generation_prompt':prompt,'generation_raw':raw,'generation_usage':usage,
                'generator':'deterministic_fallback','generation_error':type(exc).__name__}


def generate(split):
    folder=ARTIFACTS/'datasets';path=folder/f'{split}.jsonl';cards=read_jsonl(folder/f'{split}-cards.jsonl')
    existing={r['sample_id'] for r in read_jsonl(path)} if path.exists() else set()
    with ThreadPoolExecutor(max_workers=4) as pool,path.open('a',encoding='utf-8') as output:
        futures={pool.submit(generate_one,row):row for row in cards if row['sample_id'] not in existing}
        for future in as_completed(futures):
            row=futures[future]
            try:result=future.result()
            except Exception as exc:
                result={**row,'opening':'I need '+str(row['category_path'][-1])+'. '+row['facts'][0]['value'],
                        'answers':[f['value'] for f in row['facts']],'generator':'deterministic_fallback','generation_error':type(exc).__name__}
            output.write(json.dumps(result,ensure_ascii=False)+'\n');output.flush();existing.add(row['sample_id'])
            if len(existing)%50==0:print(split,len(existing),'/',len(cards),flush=True)
    write_json(path.with_suffix('.generation.json'),{'manifest':manifest({'split':split},[path]),'count':len(existing),
        'generator_counts':dict(Counter(r['generator'] for r in read_jsonl(path)))})


class Shopper:
    def __init__(self,row,protocol=False,replay=False):self.row=row;self.protocol=protocol;self.replay=replay;self.used=set()
    def message(self,turn,asked=None):
        row=self.row
        if self.protocol:
            if turn==1:return "I'm looking for "+row['coarse_category']+'. A key requirement is: '+row['protocol_card']['hard_constraints'][0]+'.'
            values=row['protocol_card']['hard_constraints']+row['protocol_card']['soft_preferences']
            candidates=[v for v in values if v not in self.used and (asked in (None,'other') or classify_constraint(v)==asked)]
            chosen=candidates[:2];self.used.update(chosen)
            return 'For that, what matters is: '+'; '.join(chosen)+'.' if chosen else "I don't have an additional preference for "+str(asked or 'other')+'.'
        if turn==1:
            self.used.add(0)
            if row['scenario']=='category_override':return 'I am looking for '+str((row['old_product']['category_path'] or ['a product'])[-1])+'.'
            if row['scenario']=='partial_override':return 'I need '+str(row['category_path'][-1])+'. My initial feature requirement is: '+row['old_product']['facts'][0]['value']
            if row['scenario']=='negation':return "I don't want "+str((row['old_product']['category_path'] or ['that other category'])[-1])+'. Instead, '+row['opening']
            prefix='Just browsing for now. ' if row['scenario'] in ('browsing','browsing_to_buying') else ''
            return prefix+row['opening']
        if row['scenario']=='category_override' and turn==2:return 'Still thinking about that category.'
        if row['scenario']=='category_override' and turn==3:
            self.used={0};return 'Actually switch to a different category. '+row['opening']
        if row['scenario']=='partial_override' and turn==3:
            return 'Actually replace my initial feature requirement with this: '+row['answers'][0]
        indices=[i for i,f in enumerate(row['facts']) if i not in self.used and (self.replay or asked in (None,'other') or f['attribute']==asked)]
        if not indices:indices=[i for i in range(len(row['facts'])) if i not in self.used]
        if not indices:return 'I have no other requirements. Which options best fit what I said?'
        i=indices[0];self.used.add(i);message=row['answers'][i]
        if row['scenario']=='browsing_to_buying' and turn==3:message='I am ready to buy now. '+message
        return message


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','generate']);parser.add_argument('--split',default='train',choices=['train','dev','test']);args=parser.parse_args()
    prepare() if args.action=='prepare' else generate(args.split)
