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
