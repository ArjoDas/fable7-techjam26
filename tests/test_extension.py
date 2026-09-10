import json
from pathlib import Path
import tempfile
import unittest
from extension.common import write_jsonl
from extension.catalog import Catalog
from extension.agent import Agent


def product(asin,color='red',category='Shirts'):
    return {'parent_asin':asin,'title':color+' cotton '+category,'categories':['Clothing',category],
            'features':['cotton',color], 'details':{'Color':color,'Material':'cotton'},'description':[],
            'price':20,'rating_number':10,'average_rating':4,'store':'Fixture'}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'input.jsonl';write_jsonl(self.path,[product('A'),product('B','blue')])
        self.store=Catalog(self.root/'store',self.path)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def test_duplicate_delete_recovery_and_replica(self):
        replica=Catalog(self.root/'store')
        try:
            e={'parent_asin':'A','revision':1,'operation':'delete'}
            self.assertEqual(self.store.apply([e]),1);self.assertEqual(self.store.apply([e]),1)
            replica.sync(1);self.assertNotIn('A',replica.agent._product_views)
            self.store.apply([{'parent_asin':'A','revision':2,'operation':'upsert','product':product('A')}])
            replica.sync(2);self.assertIn('A',replica.agent._product_views)
            self.assertEqual(self.store.metrics[-1]['derived_product_builds'],1)
            self.store.checkpoint()
            recovered=Catalog(self.root/'store')
            try:self.assertEqual(recovered.version,2);self.assertEqual(recovered.products,self.store.products)
            finally:recovered.close()
        finally:replica.close()
    def test_unregistered_and_atomic_invalid_batch(self):
        with self.assertRaises(ValueError):self.store.apply([
            {'parent_asin':'A','revision':1,'operation':'delete'},
            {'parent_asin':'UNKNOWN','revision':1,'operation':'upsert','product':product('UNKNOWN')}])
        self.assertEqual(self.store.version,0);self.assertIn('A',self.store.products)
    def test_unavailable_removed_from_evidence_and_graph(self):
        self.store.apply([{'parent_asin':'A','revision':1,'operation':'availability','available':False}])
        self.assertNotIn('A',self.store.agent._product_views)
        self.assertFalse(any('A' in ids for ids in self.store.edges.values()))
    def test_provenance_backed_new_identity(self):
        from extension.ingest import normalize
        raw=product('C');row={'raw':raw,'product':normalize(raw,'Clothing_Shoes_and_Jewelry'),
            'source_url':'https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/fixture',
            'source_category':'Clothing_Shoes_and_Jewelry','source_line':1,'source_record_sha256':'fixture'}
        self.store.register([row]);self.store.apply([{'parent_asin':'C','revision':1,'operation':'upsert','product':row['product']}])
        self.assertIn('C',self.store.agent._product_views)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'input.jsonl'
        write_jsonl(self.path,[product('A'),product('B','blue'),product('C','red','Wallets')]);self.agent=Agent(self.path)
    def tearDown(self):self.agent.base.connection.close();self.temp.cleanup()
    def test_correction_preserves_material_and_replaces_color(self):
        self.agent.reset('x',{});self.agent.respond('x','Need a red cotton shirt',1,10)
        r=self.agent.respond('x','Actually blue please',2,10)
        self.assertEqual([x['parent_asin'] for x in r['recommendations']],['B'])
        c=self.agent.trace['x']['constraints'];self.assertTrue(any(x['value']=='cotton' for x in c));self.assertFalse(any(x['value']=='red' for x in c))
    def test_false_protocol_and_material_category(self):
        self.agent.reset('x',{});self.agent.respond('x',"I'm looking for something comfy, maybe cotton?",1,10)
        self.assertNotEqual(self.agent.trace['x']['route'],'protocol');self.assertNotEqual(self.agent.trace['x']['category_alias'],'cotton')
    def test_full_switch_and_session_isolation(self):
        self.agent.reset('x',{});self.agent.reset('y',{})
        self.agent.respond('x','Need a blue shirt',1,10)
        r=self.agent.respond('x','Switch to wallets',2,10)
        self.assertEqual([x['parent_asin'] for x in r['recommendations']],['C'])
        self.assertEqual(self.agent.states['y']['constraints'],[])


class BudgetTests(unittest.TestCase):
    def test_concurrent_reservations_and_unknown_usage(self):
        from concurrent.futures import ThreadPoolExecutor
        from extension.providers import Ledger,BudgetExceeded
        with tempfile.TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'budget.sqlite')
            def reserve(i):
                try:return ledger.reserve('screen','fixture',.3,'public fixture')
                except BudgetExceeded:return None
            with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(reserve,range(20)))
            self.assertEqual(sum(i is not None for i in ids),6)
            self.assertLessEqual(ledger.summary()['charged_or_reserved_usd'],2)
            first=next(i for i in ids if i)
            ledger.finish(first,'timeout',None,{},1)
            self.assertAlmostEqual(ledger.summary()['charged_or_reserved_usd'],1.8)


class VectorTests(unittest.TestCase):
    def test_field_delta_and_compaction_do_not_reencode_unchanged(self):
        import numpy as np
        from extension.vectors import FieldVectors,VectorIndex,text,text_hash
        from extension.common import write_json
        class Encoder:
            def __init__(self):self.calls=0
            def encode(self,texts):
                self.calls+=len(texts);rows=[]
                for text in texts:
                    x=np.zeros(384,dtype='float32');x[sum(text.encode())%384]=1;rows.append(x)
                return np.stack(rows)
        encoder=Encoder();fields=FieldVectors(encoder);p=product('A')
        fields.update('A',p);before=encoder.calls;fields.update('A',p);self.assertEqual(encoder.calls,before)
        changed={**p,'title':'different title'};fields.update('A',changed);self.assertEqual(encoder.calls,before+1)
        reference=FieldVectors(Encoder());reference.update('A',changed)
        np.testing.assert_allclose(fields.vector('A'),reference.vector('A'))
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);np.save(folder/'base.npy',encoder.encode([text(p)]))
            write_json(folder/'base.json',{'ids':['A'],'text_hashes':{'A':text_hash(text(p))},'encoder_revision':'fixture'})
            index=VectorIndex(folder,encoder);before=encoder.calls;index.compact(folder/'compact')
            self.assertEqual(before,encoder.calls)
            self.assertEqual(json.loads((folder/'compact/base.json').read_text())['compaction_encoded_texts'],0)
            index.close()




class ServingTests(unittest.TestCase):
    def test_workers_acknowledge_and_revalidate_cached_retry(self):
        from extension.service import Pool
        import time
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'input.jsonl';write_jsonl(path,[product('A'),product('B','blue')])
            store=Catalog(root/'store',path);store.close();pool=Pool(2,root/'store',variant='rules')
            try:
                deadline=time.monotonic()+30
                while len(pool.ready)<2 and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(len(pool.ready),2)
                self.assertEqual(pool.submit({'operation':'reset','session_id':'x','user_profile':{}})['status'],200)
                request={'operation':'respond','session_id':'x','request_id':'one','turn':1,'top_k':10,'message':'Need a red cotton shirt'}
                first=pool.submit(request);self.assertEqual(first['status'],200)
                self.assertEqual(first['result']['recommendations'],[{'parent_asin':'A'}])
                publication=pool.publish([{'parent_asin':'A','revision':1,'operation':'delete'}])
                self.assertEqual(publication['result']['worker_acknowledgements'],[1,1])
                retry=pool.submit(request);self.assertEqual(retry['status'],200)
                self.assertEqual(retry['result']['recommendations'],[])
                self.assertEqual(retry['result']['catalog_version'],1)
                self.assertEqual(pool.submit(dict(request,message='different'))['status'],409)
                self.assertEqual(pool.submit(dict(request,request_id='two',turn=3))['status'],409)
            finally:pool.close()


class AdditionalSafetyTests(unittest.TestCase):
    def test_availability_roundtrip_retains_fact_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.jsonl';write_jsonl(path,[product('A'),product('B')]);store=Catalog(Path(folder)/'store',path)
            try:
                store.apply([{'parent_asin':'A','revision':1,'operation':'availability','available':False}])
                store.apply([{'parent_asin':'A','revision':2,'operation':'availability','available':True}])
                p=store.products['A'];store.apply([{'parent_asin':'A','revision':3,'operation':'delete'}])
                store.apply([{'parent_asin':'A','revision':4,'operation':'upsert','product':p}])
                self.assertIn('A',store.agent._product_views)
            finally:store.close()
    def test_malformed_model_references_are_rejected(self):
        from extension.providers import Matcher
        with tempfile.TemporaryDirectory() as folder:
            from extension.providers import Ledger
            matcher=Matcher(ledger=Ledger(Path(folder)/'ledger.sqlite'))
            with self.assertRaises(ValueError):matcher.validate({'ranking':['invented']},[{'ref':'0'}])
    def test_protocol_exit_retains_material(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.jsonl';write_jsonl(path,[product('A'),product('B','blue')]);agent=Agent(path)
            try:
                category=next(iter(agent.category_ids));agent.reset('x',{})
                agent.respond('x',"I'm looking for "+category+'. A key requirement is: cotton.',1,10)
                self.assertEqual(agent.trace['x']['route'],'protocol')
                agent.respond('x','Actually blue please',2,10)
                self.assertTrue(any(c['value']=='cotton' and not c['replaced'] for c in agent.states['x']['constraints']))
            finally:agent.base.connection.close()

if __name__=='__main__':unittest.main()
