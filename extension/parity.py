"""Recheck deterministic extended lexical ordering after mutation and recovery."""
import time
from extension.common import ARTIFACTS,write_json,manifest
from extension.catalog import Catalog
from extension.update_benchmark import signature


def main():
    folder=ARTIFACTS/'updates/run-1';store=Catalog(folder/'incremental');start=time.perf_counter();reference=store._build(store.products)
    queries=[]
    for a in sorted(store.products)[::600]:
        p=store.products[a]
        if p.get('available',True):queries.append(str((p.get('categories') or ['product'])[-1])+' '+' '.join(map(str,(p.get('features') or [])[:2])))
    mismatches=[]
    for query in queries:
        left=signature(store.agent,query);right=signature(reference,query)
        if left!=right:mismatches.append({'query':query,'incremental':left,'rebuilt':right})
    write_json(folder/'parity-deterministic.json',{'manifest':manifest({}),'queries':len(queries),'ordered_mismatches':len(mismatches),'examples':mismatches,'seconds':time.perf_counter()-start,
        'views_equal':store.agent._product_views==reference._product_views,'cards_equal':store.agent._dialogue_index.cards==reference._dialogue_index.cards})
    print('Deterministic parity',len(queries),'queries',len(mismatches),'mismatches',flush=True);reference.connection.close();store.close()

if __name__=='__main__':main()
