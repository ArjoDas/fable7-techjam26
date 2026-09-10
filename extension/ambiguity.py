"""Metadata ambiguity audit independent of agent rankings or held-out labels."""
from collections import defaultdict,Counter
import json
from extension.common import ARTIFACTS,read_jsonl,write_json,manifest,dataset_path
from extension.datasets import evidence


def main():
    products=read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl');postings=defaultdict(set);categories=defaultdict(set)
    for p in products:
        a=p['parent_asin'];categories[tuple(p.get('categories') or [])].add(a)
        for fact in evidence(p):postings[fact['value'].casefold()].add(a)
    results=[]
    for split in ('train','dev','test'):
        source=dataset_path(split)
        if not source.exists():continue
        for row in read_jsonl(source):
            ids=set(categories[tuple(row['category_path'])])
            for fact in row['facts']:ids.intersection_update(postings[fact['value'].casefold()])
            results.append({'sample_id':row['sample_id'],'split':split,'group':row['group'],'scenario':row['scenario'],
                'matching_catalog_records':len(ids),'target_supported':row['target'] in ids,'identifiable_from_full_evidence':len(ids)==1,
                'fits_one_top10':0<len(ids)<=10})
    write_json(ARTIFACTS/'datasets/ambiguity.json',{'manifest':manifest({'rule':'Exact source fact equality and full taxonomy path; computed without agent outputs'},[ARTIFACTS/'catalog/catalog-60000.jsonl']),
        'rows':results,'scope':'Full evidence ambiguity diagnostic, not an oracle for partial-turn language. Rankings may use additional evidence; no targets are dropped after observing performance.',
        'by_split':{s:{'tasks':sum(r['split']==s for r in results),'unique':sum(r['split']==s and r['identifiable_from_full_evidence'] for r in results),'more_than_10_matches':sum(r['split']==s and r['matching_catalog_records']>10 for r in results)} for s in ('train','dev','test')}})

if __name__=='__main__':main()
