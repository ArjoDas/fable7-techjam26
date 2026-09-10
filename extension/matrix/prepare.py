"""Freeze nested catalogs and official-evaluator tasks without generated dialogue leakage."""
from collections import defaultdict
import random
import json
from evaluator.local_evaluator import intent_card,behavior_for
from extension.matrix.common import *

def interleave(rows):
    groups=defaultdict(list)
    for p in rows:
        n=int(p.get('rating_number') or 0);band='low' if n<=10 else 'mid' if n<=100 else 'high'
        groups[(str((p.get('categories') or ['unknown'])[0]),band)].append(p)
    for key in groups:groups[key].sort(key=lambda p:stable((SEEDS[0],p['parent_asin'])))
    # Proportional, deterministic stratification at every checkpoint.
    placed={k:0 for k in groups};output=[]
    for step in range(len(rows)):
        key=max((k for k in groups if placed[k]<len(groups[k])),key=lambda k:((step+1)*len(groups[k])/len(rows)-placed[k],k))
        output.append(groups[key][placed[key]]);placed[key]+=1
    return output

def main():
    output=HOME/'prepared'
    if (output/'manifest.json').exists():return
    original=read_jsonl(ROOT/'data/catalog.jsonl');records=read_jsonl(ARTIFACTS/'catalog/additions.jsonl');products={p['parent_asin']:p for p in original};official_ids=set(products)
    products.update({r['product']['parent_asin']:r['product'] for r in records})
    original_order=interleave(original);by_category=defaultdict(list)
    for r in records:by_category[r['source_category']].append(r['product'])
    new=[];buckets={k:interleave(v) for k,v in by_category.items()}
    for i in range(2500):
        new.extend(buckets['Clothing_Shoes_and_Jewelry'][i*2:i*2+2]);new.append(buckets['Electronics'][i]);new.append(buckets['Home_and_Kitchen'][i])
    ordered=original_order+new
    write_jsonl(output/'ordered-products.jsonl',ordered);write_jsonl(output/'source-records.jsonl',records)
    schedules={name:{str(n):[p['parent_asin'] for p in ordered[:n]] for n in sizes} for name,sizes in SCHEDULES.items()}
    write_json(output/'membership.json',schedules)
    for name,sizes in SCHEDULES.items():
        write_jsonl(output/f'{name}-initial.jsonl',ordered[:sizes[0]])
        for before,after in zip(sizes,sizes[1:]):write_jsonl(output/f'{name}-{after}-events.jsonl',[{'operation':'upsert','parent_asin':p['parent_asin'],'revision':1,'product':p} for p in ordered[before:after]])
    public=read_jsonl(ROOT/'data/public_set.jsonl');exposed=set()
    for path in (ARTIFACTS/'quality').glob('test-*.json'):
        exposed.update(r['target'] for r in json.loads(path.read_text(encoding='utf-8')).get('sessions',[]))
    allocation={s:read_jsonl(ARTIFACTS/f'datasets/canonical/{s}.jsonl') for s in ('train','dev','test')};used={r['target'] for rows in allocation.values() for r in rows}|{r['ground_truth']['parent_asin'] for r in public}|exposed
    replacement_count=0
    for split,rows in allocation.items():
        output_rows=[]
        for i,row in enumerate(rows):
            target=row['target']
            if split=='test' and target in exposed:
                candidates=[p for p in ordered if p['parent_asin'] not in used and (p['parent_asin'] in official_ids)==(row['group']=='original') and (p.get('categories') or [None])[0]==row['category_path'][0]]
                if not candidates:raise RuntimeError('No fresh test replacement with matching provenance/category')
                target=min(candidates,key=lambda p:stable(p['parent_asin']))['parent_asin'];used.add(target);replacement_count+=1
            scenario=('buying','browsing','intent_override','boundary')[int(stable(row['sample_id']),16)%20//5]
            card=intent_card(products[target]);behavior=behavior_for(scenario,card,random.Random(stable(row['sample_id'])))
            output_rows.append({'sample_id':row['sample_id'],'scenario_type':scenario,'user_profile':public[i%len(public)]['user_profile'],
                'ground_truth':{'parent_asin':target},'intent_card':card,'behavior':behavior,'group':row['group'],'split':split})
        write_jsonl(output/f'{split}.jsonl',output_rows)
    write_json(output/'manifest.json',{'manifest':manifest({'schedules':SCHEDULES,'seeds':SEEDS,'old_query_banks_not_reused':True},[ROOT/'data/catalog.jsonl',ARTIFACTS/'catalog/additions.jsonl']), 'products':len(ordered),'tasks':{s:len(r) for s,r in allocation.items()},'fresh_test_replacements':replacement_count})
    print('Prepared matrix catalogs and 3200 evaluator-derived tasks',flush=True)

if __name__=='__main__':main()
