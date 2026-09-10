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


if __name__=='__main__':unittest.main()
