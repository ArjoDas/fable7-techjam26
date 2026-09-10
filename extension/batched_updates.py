"""Batched publication at scheduled update rates, with retained timing samples."""
import argparse
import time
from extension.common import ARTIFACTS,read_jsonl,write_json,write_jsonl,manifest,latency_summary
from extension.catalog import Catalog
from extension.update_benchmark import signature


def run():
    folder=ARTIFACTS/'updates/batched';folder.mkdir(parents=True,exist_ok=True)
    store=Catalog(folder/'store',ARTIFACTS/'catalog/catalog-60000.jsonl');ids=sorted(store.products);results=[]
    for rate in (1,10,100):
        samples=[];started=time.perf_counter();number=0;duration=10.;batch_size=max(1,int(rate*.1))
        while number<rate*duration:
            batch=[];scheduled=[]
            for i in range(batch_size):
                at=started+(number+i)/rate;a=ids[(number+i)%len(ids)];scheduled.append(at)
                batch.append({'parent_asin':a,'revision':store.revisions[a]+1,'operation':'availability','available':(number+i)%2==0})
            delay=scheduled[-1]-time.perf_counter()
            if delay>0:time.sleep(delay)
            begin=time.perf_counter();version=store.apply(batch);visible=time.perf_counter()
            qstart=time.perf_counter();returned=signature(store.agent,'comfortable cotton shirt');qend=time.perf_counter()
            assert all(store.products[a].get('available',True) for a in returned)
            for event,at in zip(batch,scheduled):samples.append({'event':event,'scheduled_s':at-started,'published_s':visible-started,'version':version,'update_to_visible_ms':(visible-at)*1000,'batch_apply_ms':(visible-begin)*1000,'query_ms':(qend-qstart)*1000})
            number+=batch_size
        write_jsonl(folder/f'rate-{rate}-raw.jsonl',samples)
        results.append({'offered_events_per_second':rate,'batch_size':batch_size,'elapsed_seconds':time.perf_counter()-started,'achieved_events_per_second':len(samples)/(time.perf_counter()-started),
                        'visibility':latency_summary([s['update_to_visible_ms'] for s in samples]),'search':latency_summary([s['query_ms'] for s in samples])})
        print(results[-1],flush=True)
    write_json(folder/'result.json',{'manifest':manifest({'max_batch_wait_seconds':.1}),'rates':results,'scope':'Interleaved local search; external HTTP concurrency evaluated separately'})
    store.close()

if __name__=='__main__':run()
