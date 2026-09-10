"""Measure truly unseen Amazon passage ingestion, not a precomputed future vector."""
import argparse
import re
import time
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest
from extension.catalog import Catalog
from extension.passages import PassageIndex,passages
from extension.rag import RAGAgent
from extension.rerankers import CrossEncoder


def main(label='unseen-update'):
    if not re.fullmatch('[a-z0-9-]+',label):raise ValueError('Invalid output label')
    folder=ARTIFACTS/'rag'/label
    if (folder/'catalog').exists():raise RuntimeError('Use a fresh label: repeated revisions or cached encodings would invalidate this unseen-ingestion measurement')
    store=Catalog(folder/'catalog',ROOT/'data/catalog.jsonl');vectors=PassageIndex(store);agent=RAGAgent(catalog=store,variant='weighted-rag',vectors=vectors,reranker=CrossEncoder('tinybert',limit=100))
    source=read_jsonl(ARTIFACTS/'datasets/absent-source-records.jsonl')[0];p=source['product'];a=p['parent_asin'];assert a not in store.revisions;store.register([source]);base_matrix=vectors.matrix
    before=vectors.encoded_texts;started=time.perf_counter();version=store.apply([{'parent_asin':a,'revision':1,'operation':'upsert','product':p}]);lexical=time.perf_counter()-started
    vectors.sync(store);published=time.perf_counter()-started;encoded=vectors.encoded_texts-before
    query='I need '+str(p['categories'][-1])+'. '+' '.join(map(str,p['features'][:2]));agent.reset('new',{});result=agent.respond('new',query,1,10)
    hit=a in [r['parent_asin'] for r in result['recommendations']];trace=agent.trace['new']
    before=vectors.encoded_texts;store.apply([{'parent_asin':a,'revision':2,'operation':'delete'}]);vectors.sync(store)
    deleted_not_retrieved=a not in vectors.search(query,100,store);deletion_encodes=vectors.encoded_texts-before
    before=vectors.encoded_texts;store.apply([{'parent_asin':a,'revision':3,'operation':'upsert','product':p}]);vectors.sync(store);reintroduction_encodes=vectors.encoded_texts-before
    base_unchanged=vectors.matrix is base_matrix;delta_products=len(vectors.delta_ids)
    incremental=vectors.search(query,100,store);before=vectors.encoded_texts;started=time.perf_counter();vectors.compact();compaction_seconds=time.perf_counter()-started
    compaction_encodes=vectors.encoded_texts-before;compacted=vectors.search(query,100,store)
    write_json(folder/'result.json',{'manifest':manifest({'scope':'Isolated original50k plus one real Amazon product excluded from the expanded60k; no evaluation catalog mutation'},[ARTIFACTS/'datasets/absent-source-records.jsonl']),
        'asin':a,'passages':len(passages(p)),'encoded_new_passages':encoded,'lexical_publish_seconds':lexical,'all_required_indexes_ready_seconds':published,
        'deletion_encodes':deletion_encodes,'reintroduction_encodes':reintroduction_encodes,'deleted_not_retrieved':deleted_not_retrieved,
        'base_matrix_retained_across_events':base_unchanged,'delta_products_before_compaction':delta_products,'compaction_seconds':compaction_seconds,'compaction_encodes':compaction_encodes,'compaction_retrieval_equal':incremental==compacted,
        'source_evidence_query':query,'target_hit10':hit,'response':result,'trace':trace})
    vectors.close();store.close();print('Unseen Amazon ingestion',encoded,'new passages; target Hit@10:',hit,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='unseen-update');args=parser.parse_args();main(args.label)
