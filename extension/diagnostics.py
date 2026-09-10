"""Diagnostic scoring separates clarification from hidden-target recovery."""
import argparse
from collections import Counter
from extension.common import ARTIFACTS,read_jsonl,write_json,manifest
from extension.catalog import Catalog
from extension.factory import create


def run(variant):
    source=ARTIFACTS/'datasets/diagnostics.jsonl';rows=read_jsonl(source);store=Catalog(ARTIFACTS/f'diagnostics/store-{variant}',ARTIFACTS/'catalog/catalog-60000.jsonl')
    unavailable=[r['excluded_target'] for r in rows if r['kind']=='unavailable']
    store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'availability','available':False} for a in unavailable])
    agent=create(store,variant);results=[]
    for row in rows:
        sid=row['sample_id'];agent.reset(sid,{});response=agent.respond(sid,row['query'],1,10);ids=[r['parent_asin'] for r in response['recommendations']];trace=agent.trace[sid]
        if row['kind']=='contradiction':passed=not ids and response.get('ask_attribute') is not None
        else:passed=row['excluded_target'] not in ids and all(a in store.products and store.products[a].get('available',True) for a in ids)
        results.append({'sample_id':sid,'kind':row['kind'],'passed':passed,'clarified':not ids and bool(response.get('ask_attribute')),'response':response,'trace':trace})
        agent.close(sid)
    write_json(ARTIFACTS/f'diagnostics/{variant}.json',{'manifest':manifest({'variant':variant},[source]),'results':results,
        'by_kind':{kind:{'count':sum(r['kind']==kind for r in results),'passed':sum(r['kind']==kind and r['passed'] for r in results),'clarified':sum(r['kind']==kind and r['clarified'] for r in results)} for kind in {r['kind'] for r in results}},
        'scope':'Absent targets may have supported catalog alternatives; absence of an invented ID is necessary but not proof of useful clarification.'});store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--variant',default='tinybert-lexical');a=p.parse_args();run(a.variant)
