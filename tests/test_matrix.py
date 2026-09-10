import tempfile,unittest,random
from pathlib import Path
from unittest.mock import patch
from evaluator import local_evaluator as official
from starter.agent import Agent
from extension.common import write_jsonl
from extension.matrix.events import Event,decode,canonical,render
from extension.matrix.evaluate import evaluate,summary
from extension.matrix.translate import Converter

def product(a,color):return {'parent_asin':a,'title':color+' cotton shirt','categories':['Clothing','Shirts'],'features':[color,'cotton'],'details':{},'price':20}

class MatrixTests(unittest.TestCase):
    def test_official_event_roundtrip_and_render_reproducibility(self):
        events=[Event('opening','Shirts',('cotton',)),Event('opening_old','Shirts',('red',)),Event('browse','Shirts'),Event('disclosure',values=('cotton','color: red')),Event('override',values=('cotton',)),Event('boundary',attribute='color'),Event('missing',attribute='size'),Event('ask')]
        for e in events:
            self.assertEqual(decode(canonical(e)),e)
            self.assertEqual(render(e,'wording','one',2,'dev'),render(e,'wording','one',2,'dev'))
            text,_=render(e,'wording','one',2,'dev')
            for v in e.values:self.assertIn(v,text)
    def test_experimental_constrained_loop_matches_official_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.jsonl';rows=[product('A','red'),product('B','blue')];write_jsonl(path,rows);a=Agent(path);b=Agent(path)
            try:
                samples=[]
                for i,scenario in enumerate(('buying','browsing','intent_override','boundary')):
                    card=official.intent_card(rows[0]);samples.append({'sample_id':str(i),'scenario_type':scenario,'ground_truth':{'parent_asin':'A'},'user_profile':{},'intent_card':card,'behavior':official.behavior_for(scenario,card,random.Random(3))})
                ids,categories,products=official.catalog_index(path);reference=official.evaluate(a,samples,ids,categories,products);result=summary(evaluate(b,samples,products))
                for key in ('hit_rate_at_10','mrr','mttc'):self.assertEqual(reference[key],result[key])
                self.assertAlmostEqual(reference['recommended_technical_score'],result['experimental_technical_score'],places=6)
            finally:a.connection.close();b.connection.close()
    def test_incremental_ordinals_match_rebuild_and_survive_restart(self):
        from extension.matrix.growth import OrderedCatalog
        from extension.catalog import digest
        with tempfile.TemporaryDirectory() as folder,patch('extension.matrix.growth.ordinals',return_value={'A':1,'B':2,'C':3}):
            root=Path(folder);path=root/'catalog.jsonl';write_jsonl(path,[product('A','red'),product('C','green')]);store=OrderedCatalog(root/'store',path)
            try:
                p=product('B','blue')
                with store.db:store.db.execute('INSERT INTO registry VALUES (?,?,?)',('B',digest(p),'{}'))
                store.apply([{'parent_asin':'B','revision':1,'operation':'upsert','product':p}]);reference=store._build(store.products)
                try:
                    self.assertEqual(store.rowids,{'A':1,'B':2,'C':3})
                    self.assertEqual(store.agent._dialogue_index.prefixes,reference._dialogue_index.prefixes)
                finally:reference.connection.close()
                store.checkpoint();store.close();store=OrderedCatalog(root/'store');self.assertEqual(store.rowids,{'A':1,'B':2,'C':3})
            finally:store.close()
    def test_converter_uses_only_active_evidence_and_fails_unknown_values(self):
        from extension.catalog import Catalog
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'catalog.jsonl';write_jsonl(path,[product('A','red')]);store=Catalog(root/'store',path)
            try:
                converter=Converter(store);category=next(iter(converter.categories))
                e,_=converter.convert('I need '+category+'. The important part is cotton.',{})
                self.assertEqual(e.values,('cotton',));self.assertEqual(e.kind,'opening')
                with self.assertRaises(ValueError):converter.convert('I need '+category+'. It must levitate.',{})
                store.apply([{'parent_asin':'A','revision':1,'operation':'delete'}]);converter.refresh();self.assertEqual(converter.values,set())
            finally:store.close()
    def test_converter_preserves_punctuation_and_updates_only_changed_products(self):
        from extension.catalog import Catalog
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'catalog.jsonl';a=product('A','red');a['features']=['100% Cotton','Closure Type: Pull On'];write_jsonl(path,[a,product('B','blue')]);store=Catalog(root/'store',path)
            try:
                converter=Converter(store);before=converter.processed_products
                event,_=converter.convert('My preferences are 100% Cotton; Closure Type: Pull On.',{'started':True,'asked':'other'})
                self.assertEqual(event.values,('100% cotton','closure type: pull on'))
                store.apply([{'parent_asin':'A','revision':1,'operation':'delete'}]);converter.refresh()
                self.assertEqual(converter.processed_products-before,1);self.assertIn('cotton',converter.values);self.assertNotIn('closure type: pull on',converter.values)
            finally:store.close()
    def test_matrix_worker_publication_updates_converter_before_acknowledging(self):
        from extension.catalog import Catalog
        from extension.service import Pool
        import time
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'catalog.jsonl';write_jsonl(path,[product('A','red'),product('B','blue')]);store=Catalog(root/'store',path);store.close();pool=Pool(1,root/'store',variant='matrix-rules')
            try:
                deadline=time.monotonic()+30
                while not pool.ready and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(pool.ready);self.assertEqual(pool.submit({'operation':'reset','session_id':'x'})['status'],200)
                request={'operation':'respond','session_id':'x','request_id':'one','turn':1,'top_k':10,'message':'I need shirts. The important part is color: red.'}
                self.assertEqual(pool.submit(request)['status'],200)
                update=pool.publish([{'parent_asin':'A','revision':1,'operation':'delete'}]);self.assertEqual(update['result']['worker_acknowledgements'],[1])
                retry=pool.submit(request);self.assertEqual(retry['result']['recommendations'],[])
            finally:pool.close()

if __name__=='__main__':unittest.main()
