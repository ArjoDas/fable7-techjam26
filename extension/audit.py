"""Retained absent-Amazon diagnostics and reproducible generation-defect audit."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import io
import json
import random
import re
import urllib.request
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,write_jsonl,manifest
from extension.ingest import normalize,SOURCES


def diagnostic_sources():
    path=ARTIFACTS/'datasets/absent-source-records.jsonl'
    if path.exists():return
    excluded={p['parent_asin'] for p in read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')};rows=[]
    for source,count in zip(SOURCES,(34,33,33)):
        url=f'https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories/meta_{source}.jsonl.gz';selected=[]
        with urllib.request.urlopen(url,timeout=90) as response,gzip.GzipFile(fileobj=response) as gz,io.TextIOWrapper(gz,encoding='utf-8') as stream:
            for number,line in enumerate(stream,1):
                raw=json.loads(line);a=raw.get('parent_asin')
                if a and a not in excluded and raw.get('features') and raw.get('categories'):
                    selected.append({'raw':raw,'product':normalize(raw,source),'source_url':url,'source_line':number,'source_record_sha256':hashlib.sha256(line.encode()).hexdigest(),'source_category':source});excluded.add(a)
                    if len(selected)==count:break
        rows.extend(selected)
    write_jsonl(path,rows);write_json(path.with_suffix('.manifest.json'),manifest({'scope':'Real source products absent from active 60k'},[path]))


def diagnostics():
    products=read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl');rows=[]
    for i,p in enumerate(products[50000:50100]):
        category=str((p.get('categories') or ['product'])[-1]);fact=str((p.get('features') or [''])[0])
        rows.append({'sample_id':f'contradiction-{i}','kind':'contradiction','query':f'I need a {category}, red and not red at the same time.','expected':'clarification','source_asin':p['parent_asin']})
        rows.append({'sample_id':f'unavailable-{i}','kind':'unavailable','query':f'I need {category}. {fact}','excluded_target':p['parent_asin'],'expected':'never_return_excluded','source_asin':p['parent_asin']})
    for i,r in enumerate(read_jsonl(ARTIFACTS/'datasets/absent-source-records.jsonl')):
        p=r['product'];rows.append({'sample_id':f'absent-{i}','kind':'absent','query':'I need '+str(p['categories'][-1])+'. '+str(p['features'][0]),'excluded_target':p['parent_asin'],'expected':'clarification_or_supported_alternative','source_asin':p['parent_asin']})
    write_jsonl(ARTIFACTS/'datasets/diagnostics.jsonl',rows)


def audit():
    products={p['parent_asin']:p for p in read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')};all_ids=set();split_ids={};defects=[];counts={};openings=Counter()
    for split in ('train','dev','test'):
        path=ARTIFACTS/f'datasets/{split}.jsonl';rows=read_jsonl(path);ids={r['target'] for r in rows};split_ids[split]=ids
        if all_ids&ids:raise RuntimeError('Target split leakage')
        all_ids|=ids;counts[split]=len(rows)
        for row in rows:
            p=products[row['target']];text=' '.join([row['opening'],*row['answers']]);normalized=re.sub(r'\W+',' ',text.lower());title=re.sub(r'\W+',' ',str(p.get('title') or '').lower()).strip()
            flags=[]
            if row['target'] in text or re.search(r'\bB0[A-Z0-9]{8}\b',text):flags.append('identifier_leakage')
            if len(title)>12 and title in normalized:flags.append('exact_title_leakage')
            title_tokens=title.split();phrases=[' '.join(title_tokens[i:i+8]) for i in range(max(0,len(title_tokens)-7))]
            if any(phrase in normalized for phrase in phrases):flags.append('eight_word_title_overlap')
            if row['generator']=='deterministic_fallback':flags.append('generation_fallback')
            if len(row['answers'])!=len(row['facts']):flags.append('answer_count')
            openings[re.sub(r'\W+',' ',row['opening'].lower())]+=1
            if flags:defects.append({'sample_id':row['sample_id'],'split':split,'flags':flags})
    dev=read_jsonl(ARTIFACTS/'datasets/dev.jsonl');groups=defaultdict(list)
    for row in dev:groups[(row['group'],row['scenario'])].append(row)
    rng=random.Random(20260910)
    for group in groups.values():rng.shuffle(group)
    selected=[]
    while len(selected)<min(200,len(dev)):
        for key in sorted(groups):
            if groups[key] and len(selected)<200:selected.append(groups[key].pop())
    write_jsonl(ARTIFACTS/'datasets/audit-dev-200.jsonl',selected)
    write_json(ARTIFACTS/'datasets/audit.json',{'manifest':manifest({'seed':20260910},[ARTIFACTS/f'datasets/{s}.jsonl' for s in counts]),'counts':counts,
        'unique_targets':len(all_ids),'split_disjoint':True,'duplicate_openings':sum(n-1 for n in openings.values() if n>1),'defects':defects,
        'dev_audit_size':len(selected),'review_type':'Automated structural checks; semantic model audit recorded separately, not human validation'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fetch','diagnostics','audit']);a=p.parse_args()
    {'fetch':diagnostic_sources,'diagnostics':diagnostics,'audit':audit}[a.action]()
