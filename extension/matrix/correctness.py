"""Catalog mutation/recovery checks in an isolated copy of the expanded snapshot."""
import copy,json,time
from extension.matrix.common import *
from extension.matrix.growth import OrderedCatalog,compare
from extension.matrix.translate import TranslatedAgent

def main():
    path=HOME/'correctness/result.json'
    if path.exists():return
    store=OrderedCatalog(HOME/'correctness/store',HOME/'snapshots/expanded-60000.jsonl');ids=sorted(store.products,key=stable);measurements=[]
    try:
        for fraction in (.001,.01,.1):
            selected=ids[:int(len(ids)*fraction)];events=[{'parent_asin':a,'operation':'availability','available':False,'revision':store.revisions[a]+1} for a in selected]
            began=time.perf_counter();store.apply(events);elapsed=time.perf_counter()-began
            withdrawn=set(selected);leaked=withdrawn&set(store.agent._product_views);prefix_leaks=sum(any(a in withdrawn for a in v) for v in store.agent._dialogue_index.prefixes.values())
            if leaked or prefix_leaks:raise AssertionError('Unavailable product remains indexed')
            version=store.version;store.apply(events);duplicate=store.version==version;store.apply([{**e,'revision':1} for e in events]);stale=store.version==version
            store.apply([{**e,'available':True,'revision':e['revision']+1} for e in events]);measurements.append({'fraction':fraction,'products':len(selected),'withdraw_seconds':elapsed,'leaks':len(leaked),'prefix_leaks':prefix_leaks,'duplicate_idempotent':duplicate,'stale_rejected':stale})
        source=read_jsonl(HOME/'prepared/source-records.jsonl')[0];withdraw=copy.deepcopy(source);withdraw['withdraw_fields']=['features','details'];withdraw['product']['features']=[];withdraw['product']['details']={};store.register([source,withdraw]);a=source['product']['parent_asin']
        agent=TranslatedAgent(store);before=agent.converter.processed_products
        store.apply([{'parent_asin':a,'operation':'upsert','revision':store.revisions[a]+1,'product':withdraw['product']}]);agent.sync_catalog();processed=agent.converter.processed_products-before
        store.apply([{'parent_asin':a,'operation':'delete','revision':store.revisions[a]+1}]);agent.sync_catalog();assert a not in agent.converter.product_evidence
        store.apply([{'parent_asin':a,'operation':'upsert','revision':store.revisions[a]+1,'product':source['product']}]);agent.sync_catalog()
        version=store.version;facts=copy.deepcopy(store.products);store.close();store=OrderedCatalog(HOME/'correctness/store');recovered=store.products==facts and store.version==version
        parity=compare(store)
        passed=recovered and processed==1 and not parity['conversation_mismatches'] and all(r['duplicate_idempotent'] and r['stale_rejected'] for r in measurements)
        write_json(path,{'manifest':manifest({'mutations':'Experimental availability, deletion/reintroduction and source-backed field withdrawal; not Amazon historical events'}),'measurements':measurements,'converter_products_reprocessed':processed,'restart_recovered':recovered,'parity':parity,'passed':passed})
        if not passed:raise RuntimeError('Matrix incremental correctness gate failed')
    finally:store.close()

if __name__=='__main__':main()
