"""Measure fixed-encoder work across insertion, withdrawal, deletion and compaction."""
import copy
import time
from extension.common import ARTIFACTS,ROOT,read_jsonl,write_json,manifest
from extension.catalog import Catalog
from extension.vectors import VectorIndex


def main():
    folder=ARTIFACTS/'vectors/update-probe';store=Catalog(folder/'catalog',ROOT/'data/catalog.jsonl');index=VectorIndex(ARTIFACTS/'vectors/document');results=[]
    def sync(name):
        before=index.encoded_texts;began=time.perf_counter();index.sync(store)
        row={'event':name,'seconds':time.perf_counter()-began,'encoded_documents':index.encoded_texts-before,'version':store.version,'tombstones':len(index.tombstones)};results.append(row);print(row,flush=True)
    sync('initial-original-50000')
    row=read_jsonl(ARTIFACTS/'catalog/additions.jsonl')[0];a=row['product']['parent_asin'];store.register([row]);store.apply([{'parent_asin':a,'revision':store.revisions.get(a,0)+1,'operation':'upsert','product':row['product']}]);sync('add-precomputed-new-product')
    changed=copy.deepcopy(row);changed['withdraw_fields']=['features'];changed['product']['features']=[];store.register([changed]);store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'upsert','product':changed['product']}]);sync('withdraw-one-product-feature-field')
    store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'delete'}]);sync('delete')
    assert a in index.tombstones
    store.apply([{'parent_asin':a,'revision':store.revisions[a]+1,'operation':'upsert','product':changed['product']}]);sync('reintroduce-identical-text')
    before=index.encoded_texts;began=time.perf_counter();index.compact(folder/'compacted');results.append({'event':'compaction','seconds':time.perf_counter()-began,'encoded_documents':index.encoded_texts-before})
    write_json(folder/'result.json',{'manifest':manifest({}),'measurements':results,'precomputed_new_product_note':'Insertion reused a vector encoded during initial 60k preparation; that earlier 10k encoding cost remains separately recorded.'})
    index.close();store.close()

if __name__=='__main__':main()
