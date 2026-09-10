"""Stable original ordinals and independent rebuild checks at catalog checkpoints."""
import argparse,json,time,sqlite3
from extension.catalog import Catalog,digest
from extension.matrix.common import *

def ordinals():
    original=read_jsonl(ROOT/'data/catalog.jsonl');ids=[p['parent_asin'] for p in original];known=set(ids)
    ids.extend(p['parent_asin'] for p in read_jsonl(HOME/'prepared/ordered-products.jsonl') if p['parent_asin'] not in known)
    return {a:i+1 for i,a in enumerate(ids)}

class OrderedCatalog(Catalog):
    def __init__(self,*args,**kwargs):self.ordinals=ordinals();super().__init__(*args,**kwargs)
    def _build(self,products):
        agent=super()._build(dict(sorted(products.items(),key=lambda item:self.ordinals[item[0]])))
        rows=list(agent.connection.execute('SELECT * FROM products'))
        with agent.connection:
            agent.connection.execute('DELETE FROM products')
            agent.connection.executemany('INSERT INTO products(rowid,parent_asin,coarse_category,title,categories,features,details,store,description) VALUES (?,?,?,?,?,?,?,?,?)',[(self.ordinals[row[0]],*row) for row in rows])
        return agent
    def _splice(self,replacement,changed):
        super()._splice(replacement,changed);rows=[]
        with self.agent.connection:
            for a in changed:
                row=self.agent.connection.execute('SELECT * FROM products WHERE rowid=?',(self.rowids.get(a,-1),)).fetchone()
                if row:rows.append(row);self.agent.connection.execute('DELETE FROM products WHERE rowid=?',(self.rowids[a],))
            self.agent.connection.executemany('INSERT INTO products(rowid,parent_asin,coarse_category,title,categories,features,details,store,description) VALUES (?,?,?,?,?,?,?,?,?)',[(self.ordinals[row[0]],*row) for row in rows])
        self.rowids.update({row[0]:self.ordinals[row[0]] for row in rows})
        for key in replacement._dialogue_index.prefixes:self.agent._dialogue_index.prefixes[key].sort(key=lambda a:self.ordinals[a])

def register_batch(store,events):
    official={p['parent_asin']:p for p in read_jsonl(ROOT/'data/catalog.jsonl')};additions={r['product']['parent_asin']:r for r in read_jsonl(HOME/'prepared/source-records.jsonl')}
    upstream=[];catalog_hash=sha256(ROOT/'data/catalog.jsonl')
    with store.db:
        for event in events:
            a=event['parent_asin'];p=event['product']
            if a in official:
                if p!=official[a]:raise ValueError('Addition disagrees with official product')
                store.db.execute('INSERT OR IGNORE INTO registry VALUES (?,?,?)',(a,digest(p),json.dumps({'official_catalog_sha256':catalog_hash,'ordinal':store.ordinals[a]})))
            else:upstream.append(additions[a])
    if upstream:store.register(upstream)

def compare(store,limit=120):
    from extension.matrix.evaluate import evaluate,summary
    started=time.perf_counter();reference=store._build(store.products);rebuild=time.perf_counter()-started
    tasks=[r for r in read_jsonl(HOME/'prepared/dev.jsonl') if r['ground_truth']['parent_asin'] in store.products][:limit]
    left=evaluate(store.agent,tasks,store.products,'constrained',SEEDS[0]);right=evaluate(reference,tasks,store.products,'constrained',SEEDS[0])
    differences=[]
    for a,b in zip(left,right):
        if [(t['recommendations'],t['candidate_ids']) for t in a['turns']]!=[(t['recommendations'],t['candidate_ids']) for t in b['turns']]:differences.append(a['sample_id'])
    result={'rebuild_seconds':rebuild,'tasks':len(tasks),'conversation_mismatches':differences,
        'views_equal':store.agent._product_views==reference._product_views,'cards_equal':store.agent._dialogue_index.cards==reference._dialogue_index.cards,
        'prefixes_equal':store.agent._dialogue_index.prefixes==reference._dialogue_index.prefixes,'aggregate':summary(left)}
    reference.connection.close();return result

def stage(schedule,size):
    sizes=SCHEDULES[schedule]
    if size not in sizes:raise ValueError('Unknown checkpoint')
    folder=HOME/'catalogs'/schedule;began=time.perf_counter();store=OrderedCatalog(folder,HOME/f'prepared/{schedule}-initial.jsonl');startup=time.perf_counter()-began
    try:
        for count in sizes:
            if count>size:break
            report=HOME/f'growth/{schedule}-{count}.json'
            if report.exists():
                previous=json.loads(report.read_text(encoding='utf-8'))['parity']
                if previous['conversation_mismatches'] or not all(previous[k] for k in ('views_equal','cards_equal','prefixes_equal')):raise RuntimeError('Previously failed parity checkpoint cannot be skipped')
                if len(store.products)==count and not (HOME/f'published/{schedule}-{count}/catalog.sqlite').exists():publish(store,schedule,count)
                continue
            began=time.perf_counter();events=[]
            already_published=False
            if count!=sizes[0]:
                events=read_jsonl(HOME/f'prepared/{schedule}-{count}-events.jsonl');already_published=all(store.revisions.get(e['parent_asin'],0)>=e['revision'] for e in events)
                register_batch(store,events);store.apply(events)
            if len(store.agent._product_views)!=count:raise RuntimeError('Unexpected active size; refusing to rewrite a prior checkpoint')
            incremental=None if already_published else time.perf_counter()-began
            timing_path=HOME/f'growth-timings/{schedule}-{count}.json'
            if timing_path.exists():incremental=json.loads(timing_path.read_text(encoding='utf-8'))['incremental_seconds']
            else:write_json(timing_path,{'incremental_seconds':incremental,'resumed_after_publication':already_published})
            store.checkpoint();publish(store,schedule,count)
            snapshot=HOME/f'snapshots/{schedule}-{count}.jsonl';write_jsonl(snapshot,[store.products[a] for a in sorted(store.products,key=lambda a:store.ordinals[a])])
            parity=compare(store)
            write_json(report,{'manifest':manifest({'schedule':schedule,'size':count,'ordinal_lookup':'rowid'},[snapshot]),'startup_seconds':startup,'initial_preprocessing_seconds':startup if count==sizes[0] else None,'incremental_seconds':incremental,'resumed_after_publication':already_published,'added':len(events),'version':store.version,'parity':parity,'snapshot':str(snapshot)})
            if parity['conversation_mismatches'] or not all(parity[k] for k in ('views_equal','cards_equal','prefixes_equal')):raise RuntimeError('Incremental/rebuild parity gate failed')
            print('Catalog checkpoint',schedule,count,'parity passed',flush=True)
    finally:store.close()

def publish(store,schedule,count):
    from extension.index import save_agent
    folder=HOME/f'published/{schedule}-{count}';folder.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(folder/'catalog.sqlite')
    try:store.db.backup(db)
    finally:db.close()
    save_agent(store.agent,folder/f'snapshot-{store.version}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--schedule',choices=SCHEDULES,required=True);p.add_argument('--size',type=int,required=True);a=p.parse_args();stage(a.schedule,a.size)
