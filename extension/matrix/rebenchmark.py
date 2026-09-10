"""Retain old update timings and remeasure from identical prior snapshots."""
import time,argparse
from extension.matrix.common import *
from extension.matrix.growth import OrderedCatalog,register_batch,compare

def main(schedule,size):
    sizes=SCHEDULES[schedule];previous=sizes[sizes.index(size)-1];folder=HOME/f'optimized-growth/{schedule}-{size}';result=folder/'result.json'
    if result.exists():return
    attempts=[int(p.name.split('-')[-1]) for p in folder.glob('attempt-*') if p.is_dir()];attempt=folder/f'attempt-{max(attempts,default=0)+1}'
    store=OrderedCatalog(attempt,HOME/f'snapshots/{schedule}-{previous}.jsonl')
    try:
        events=read_jsonl(HOME/f'prepared/{schedule}-{size}-events.jsonl');began=time.perf_counter();register_batch(store,events);store.apply(events);elapsed=time.perf_counter()-began
        parity=compare(store);write_json(result,{'manifest':manifest({'schedule':schedule,'size':size,'reason':'Direct rowid lookup replaces prior FTS scan'},[HOME/f'prepared/{schedule}-{size}-events.jsonl']), 'added':len(events),'incremental_seconds':elapsed,'parity':parity,'original_result_preserved':str(HOME/f'growth/{schedule}-{size}.json')})
        if parity['conversation_mismatches']:raise RuntimeError('Optimized growth parity failed')
        print('Optimized addition',len(events),'products:',elapsed,'seconds',flush=True)
    finally:store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--schedule',required=True);p.add_argument('--size',type=int,required=True);a=p.parse_args();main(a.schedule,a.size)
