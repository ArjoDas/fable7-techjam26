"""Clean-cache preprocessing work; never reuse vectors for future catalog products."""
import argparse,time
from extension.matrix.common import *
from extension.matrix.growth import OrderedCatalog,register_batch
from extension.passages import PassageIndex,passages,key
from extension.models import Embeddings

def main(schedule,gpu=False):
    root=HOME/f'embedding-work/{schedule}';result=root/'result.json'
    if result.exists():return
    attempts=[int(p.name.split('-')[-1]) for p in root.glob('attempt-*') if p.is_dir()];folder=root/f'attempt-{max(attempts,default=0)+1}'
    write_json(folder/'attempt.json',{'manifest':manifest({'schedule':schedule,'gpu':gpu}),'prior_incomplete_attempts':attempts,'clean_cache':True})
    sizes=SCHEDULES[schedule];began=time.perf_counter();store=OrderedCatalog(folder/'store',HOME/f'prepared/{schedule}-initial.jsonl');catalog_initial_seconds=time.perf_counter()-began;encoder=Embeddings(gpu=gpu,fp32=True)
    def preload(products):
        present={r[0] for r in vectors.db.execute('SELECT hash FROM vectors')};texts={key(t):t for p in products for t in passages(p)};missing=[t for h,t in texts.items() if h not in present]
        for start in range(0,len(missing),128):
            batch=missing[start:start+128];encoded=encoder.encode(batch)
            with vectors.db:vectors.db.executemany('INSERT INTO vectors VALUES (?,?)',[(key(t),v.tobytes()) for t,v in zip(batch,encoded)])
            vectors.encoded_texts+=len(batch)
            if start%4096==0:print('Clean-cache passages',start+len(batch),'/',len(missing),flush=True)
    began=time.perf_counter();vectors=PassageIndex(store,encoder,namespace='cold',use_base_cache=False,defer_sync=True);preload(store.products.values());vectors.sync(store);rows=[{'size':sizes[0],'seconds':time.perf_counter()-began,'catalog_initial_seconds':catalog_initial_seconds,'encoded_passages':vectors.encoded_texts,'initial':True}]
    try:
        for size in sizes[1:]:
            events=read_jsonl(HOME/f'prepared/{schedule}-{size}-events.jsonl');register_batch(store,events);before=vectors.encoded_texts;began=time.perf_counter();store.apply(events);preload([e['product'] for e in events]);vectors.sync(store)
            rows.append({'size':size,'seconds':time.perf_counter()-began,'encoded_passages':vectors.encoded_texts-before,'added_products':len(events),'delta_products':len(vectors.delta_ids),'initial':False});write_json(folder/'progress.json',rows)
        a=next(iter(store.products));p=store.products[a];before=vectors.encoded_texts
        store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'delete'}]);vectors.sync(store);deleted=a not in vectors.ids
        store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'upsert','product':p}]);vectors.sync(store);vectors.compact()
        write_json(result,{'manifest':manifest({'schedule':schedule,'gpu':gpu,'future_vector_cache_disabled':True}), 'measurements':rows,'deletion_removed':deleted,'delete_reintroduce_compact_encodes':vectors.encoded_texts-before,'encoder_weights_unchanged':True})
    finally:vectors.close();store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--schedule',required=True);p.add_argument('--gpu',action='store_true');a=p.parse_args();main(a.schedule,a.gpu)
