"""Rebuild parity, catalog growth, update streams and crash recovery experiments."""
import argparse
import copy
import json
from pathlib import Path
import random
import time
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,write_jsonl,manifest,latency_summary
from extension.catalog import Catalog
from starter.agent import _terms


def signature(agent,query):
    from extension.lexical import Lexical
    return Lexical(agent)._fused_search(list(dict.fromkeys(_terms(query)))[:80],100,route_limit=200)


def run(label):
    folder=ARTIFACTS/'updates'/label;folder.mkdir(parents=True,exist_ok=True)
    store=Catalog(folder/'incremental',ROOT/'data/catalog.jsonl');additions=read_jsonl(ARTIFACTS/'catalog/additions.jsonl');store.register(additions)
    streams=read_jsonl(folder/'events.jsonl') if (folder/'events.jsonl').exists() else []
    results=json.loads((folder/'progress.json').read_text()) if (folder/'progress.json').exists() else [];revision=1
    def apply(events,name):
        nonlocal revision
        started=time.perf_counter();version=store.apply(events);elapsed=time.perf_counter()-started
        streams.append({'name':name,'events':events,'version':version});write_jsonl(folder/'events.jsonl',streams)
        row={'name':name,'version':version,'events':len(events),'seconds':elapsed,'active':len(store.agent._product_views),
             'index_work':store.metrics[-1] if events else {}}
        results.append(row);write_json(folder/'progress.json',results);print(row,flush=True);return row
    def compare(name,targets):
        start=time.perf_counter();reference=store._build(store.products);rebuild=time.perf_counter()-start
        queries=[]
        for a in targets:
            p=store.products.get(a)
            if p and p.get('available',True):queries.append(' '.join([str((p.get('categories') or ['product'])[-1]),*map(str,(p.get('features') or [])[:2])]))
        mismatches=[];sets=[]
        for q in queries:
            left=signature(store.agent,q);right=signature(reference,q)
            if left!=right:mismatches.append({'query':q,'incremental':left,'rebuild':right})
            if set(left)!=set(right):sets.append(q)
        views=store.agent._product_views==reference._product_views
        cards=store.agent._dialogue_index.cards==reference._dialogue_index.cards
        reference.connection.close()
        output={'name':name,'full_rebuild_seconds':rebuild,'queries':len(queries),'ordered_mismatches':len(mismatches),'pool_mismatches':len(sets),'views_equal':views,'cards_equal':cards,'examples':mismatches[:10]}
        write_json(folder/f'parity-{name}.json',output);print('parity',output|{'examples':'retained'},flush=True);return output
    if store.version<12:
        parity=[];offset=0
        for total in (1000,5000,10000):
            items=additions[offset:total]
            apply([{'parent_asin':r['product']['parent_asin'],'revision':1,'operation':'upsert','product':r['product']} for r in items],f'growth-{total}')
            parity.append(compare(f'growth-{total}',list(store.products)[::601]+[r['product']['parent_asin'] for r in items[::max(1,len(items)//50)]]));offset=total
        ids=sorted(store.products);rng=random.Random(20260910)
        for fraction in (.001,.01,.1):
            selected=rng.sample(ids,int(len(ids)*fraction))
            events=[{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'availability','available':False} for a in selected]
            apply(events,f'unavailable-{fraction}')
            leaked=[a for a in selected if a in store.agent._product_views or a in store.agent._dialogue_index.cards]
            results[-1]['unavailable_leaks']=len(leaked)
            apply([dict(e,revision=e['revision']+1,available=True) for e in events],f'reavailable-{fraction}')
        # Source-backed metadata withdrawal/revelation is an experimental ingestion
        # event, never a fabricated historical change in Amazon's product facts.
        projections=[]
        for original in additions[:100]:
            row=copy.deepcopy(original);row['withdraw_fields']=['features','details'];row['product']['features']=[];row['product']['details']={};projections.append(row)
        store.register(projections)
        apply([{'parent_asin':r['product']['parent_asin'],'revision':store.revisions[r['product']['parent_asin']]+1,'operation':'upsert','product':r['product']} for r in projections],'metadata-withdrawal')
        apply([{'parent_asin':r['product']['parent_asin'],'revision':store.revisions[r['product']['parent_asin']]+1,'operation':'upsert','product':r['product']} for r in additions[:100]],'metadata-restored')
        saved={a:store.products[a] for a in ids[:100]}
        deletion=[{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'delete'} for a in saved]
        apply(deletion,'delete');before=store.version;store.apply(deletion);duplicate_unchanged=store.version==before
        store.apply([dict(e,revision=1) for e in deletion]);stale_unchanged=store.version==before
        apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'upsert','product':p} for a,p in saved.items()],'reintroduction')
    else:
        parity=[json.loads(p.read_text()) for p in sorted(folder.glob('parity-growth-*.json'))]
        ids=sorted({p['parent_asin'] for p in read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')})
        deletion=next(r['events'] for r in streams if r['name']=='delete')
        deleted_ids={e['parent_asin'] for e in deletion};source={p['parent_asin']:p for p in read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')}
        before=store.version;store.apply(deletion);duplicate_unchanged=store.version==before
        store.apply([dict(e,revision=1) for e in deletion]);stale_unchanged=store.version==before
        apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'upsert','product':{**source[a],'available':True}} for a in deleted_ids],'reintroduction')
    rates=[]
    for rate in (1,10,100):
        n=rate*10;start=time.perf_counter();visible=[];query_ms=[]
        for i in range(n):
            scheduled=start+i/rate;delay=scheduled-time.perf_counter()
            if delay>0:time.sleep(delay)
            a=ids[i%len(ids)];store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'availability','available':i%2==0}])
            visible.append((time.perf_counter()-scheduled)*1000)
            began=time.perf_counter();signature(store.agent,'comfortable cotton shirt');query_ms.append((time.perf_counter()-began)*1000)
        rates.append({'scheduled_events_per_second':rate,'events':n,'elapsed_seconds':time.perf_counter()-start,'update_to_visible':latency_summary(visible),'interleaved_search_latency':latency_summary(query_ms),
                      'note':'Single-coordinator interleaved search; scheduled backlog included. HTTP concurrent test is separate.'})
    parity.append(compare('final',ids[::600]))
    version=store.version;views=store.agent._product_views.copy();store.close()
    recovered=Catalog(folder/'incremental');recovery=version==recovered.version and views==recovered.agent._product_views;recovered.checkpoint();recovered.close()
    write_json(folder/'result.json',{'manifest':manifest({'label':label},[ARTIFACTS/'catalog/additions.jsonl']),'updates':results,'parity':parity,'rates':rates,'duplicate_idempotent':duplicate_unchanged,'stale_rejected':stale_unchanged,'restart_equal':recovery})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',default='run-1');a=p.parse_args();run(a.label)
