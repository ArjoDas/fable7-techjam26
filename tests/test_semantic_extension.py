"""Focused tests for semantic-update work and parser-before-retrieval routing."""
import tempfile
from pathlib import Path
import unittest
import numpy as np
from extension.common import write_jsonl
from extension.catalog import Catalog
from extension.rag import RAGAgent
from extension.passages import PassageIndex


def product(a,color):return {'parent_asin':a,'title':color+' shirt','categories':['Clothing','Shirts'],'features':[color,'cotton'],'details':{},'price':20}


class Encoder:
    def __init__(self):self.calls=0
    def encode(self,texts):
        self.calls+=len(texts);vectors=[]
        for text in texts:
            vector=np.zeros(384,dtype='float32');vector[sum(text.encode())%384]=1;vectors.append(vector)
        return np.stack(vectors)


class SemanticTests(unittest.TestCase):
    def test_passage_deletion_reintroduction_uses_retained_vectors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'catalog.jsonl';p=product('fixture-A','red');write_jsonl(path,[p,product('fixture-B','blue')]);catalog=Catalog(root/'store',path);encoder=Encoder();index=PassageIndex(catalog,encoder)
            try:
                before=encoder.calls;catalog.apply([{'parent_asin':'fixture-A','revision':1,'operation':'delete'}]);index.sync(catalog)
                self.assertEqual(encoder.calls,before);self.assertNotIn('fixture-A',index.ids)
                catalog.apply([{'parent_asin':'fixture-A','revision':2,'operation':'upsert','product':p}]);index.sync(catalog)
                self.assertEqual(encoder.calls,before);self.assertIn('fixture-A',index.ids)
            finally:index.close();catalog.close()
    def test_replacing_scoped_requirement_keeps_unrelated_preferences(self):
        from extension.scoped_state import ScopedRAGAgent
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.jsonl';write_jsonl(path,[product('A','red'),product('B','blue')]);agent=ScopedRAGAgent(path)
            try:
                agent.reset('x',{});agent.respond('x','Need a red shirt under $25. My initial feature requirement is: leather',1,10)
                result=agent.respond('x','Replace my initial feature requirement with this: washable',2,10)
                constraints=agent.trace['x']['constraints'];self.assertFalse(any(c['value']=='leather' for c in constraints));self.assertTrue(any(c['value']=='red' for c in constraints));self.assertTrue(any(c['attribute']=='budget' for c in constraints))
                self.assertEqual(result['recommendations'],[{'parent_asin':'A'}])
            finally:agent.base.connection.close()
    def test_category_switch_preserves_global_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.jsonl';write_jsonl(path,[product('A','red'),{'parent_asin':'B','title':'wallet','categories':['Accessories','Wallets'],'features':['leather'],'details':{},'price':50}]);agent=RAGAgent(path)
            try:
                agent.reset('x',{});agent.respond('x','Need a shirt under $25',1,10)
                result=agent.respond('x','Switch to wallets',2,10)
                self.assertTrue(any(c['attribute']=='budget' and c['value']==25 for c in agent.trace['x']['constraints']))
                self.assertEqual(result['recommendations'],[])
            finally:agent.base.connection.close()
    def test_metadata_update_encodes_only_changed_passages(self):
        from extension.ingest import normalize
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'catalog.jsonl';original=product('fixture-A','red');write_jsonl(path,[original,product('fixture-B','blue')]);catalog=Catalog(root/'store',path);encoder=Encoder();index=PassageIndex(catalog,encoder)
            try:
                before=encoder.calls;other=index.product_vectors['fixture-B'].copy();base_matrix=index.matrix;changed={**original,'features':['red','cotton','lightweight']}
                record={'raw':changed,'product':normalize(changed,'Clothing_Shoes_and_Jewelry'),'source_url':'https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/fixture',
                        'source_category':'Clothing_Shoes_and_Jewelry','source_line':1,'source_record_sha256':'fixture'}
                catalog.register([record]);catalog.apply([{'parent_asin':'fixture-A','revision':1,'operation':'upsert','product':record['product']}]);index.sync(catalog)
                self.assertEqual(encoder.calls-before,1);np.testing.assert_array_equal(other,index.product_vectors['fixture-B'])
                self.assertIs(index.matrix,base_matrix);self.assertEqual(index.delta_ids,['fixture-A'])
                self.assertFalse(index.base_active[index.base_positions['fixture-A']])
                queries=['lightweight cotton shirt','blue shirt','red clothing']
                incremental=[index.search(q,100) for q in queries];before=encoder.calls
                index.compact();self.assertEqual(encoder.calls,before);self.assertEqual(index.delta_ids,[])
                self.assertEqual(incremental,[index.search(q,100) for q in queries])
            finally:index.close();catalog.close()
    def test_parser_runs_before_retrieval_once_and_protocol_bypasses_it(self):
        class Parser:
            def __init__(self):self.calls=0
            def match(self,query,cards,timeout):self.calls+=1;return {'query':'blue cotton shirt'},{}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.jsonl';write_jsonl(path,[product('A','red'),product('B','blue')]);parser=Parser();agent=RAGAgent(path,parser=parser)
            try:
                agent.reset('p',{});category=next(iter(agent.category_ids));agent.respond('p',"I'm looking for "+category+'. A key requirement is: cotton.',1,10);self.assertEqual(parser.calls,0)
                agent.respond('p','Something blue instead, please',2,10);self.assertEqual(parser.calls,1)
                self.assertEqual(agent.trace['p']['parser']['normalized_query'],'blue cotton shirt')
                self.assertTrue(any(c['value']=='cotton' for c in agent.trace['p']['constraints']))
            finally:agent.base.connection.close()

if __name__=='__main__':unittest.main()
