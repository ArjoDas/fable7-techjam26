"""Shared-subset representation probes: document vectors, field deltas and centroids."""
from collections import defaultdict
import copy
import json
import random
import time
import numpy as np
from extension.common import ARTIFACTS,read_jsonl,write_json,write_jsonl,manifest
from extension.models import Embeddings
from extension.vectors import FieldVectors,VectorIndex,FIELDS,text


def run():
    folder=ARTIFACTS/'representations';folder.mkdir(parents=True,exist_ok=True)
    products=read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl');byid={p['parent_asin']:p for p in products}
    dev=sorted(read_jsonl(ARTIFACTS/'datasets/dev.jsonl'),key=lambda r:r['sample_id'])[:100]
    selected={r['target'] for r in dev};rng=random.Random(20260910);rng.shuffle(products)
    for p in products:
        if len(selected)>=1000:break
        selected.add(p['parent_asin'])
    ids=sorted(selected);items={a:byid[a] for a in ids};write_jsonl(folder/'shared-products.jsonl',[items[a] for a in ids])
    encoder=Embeddings(fp32=True);fields=FieldVectors(encoder);started=time.perf_counter()
    needed=list(dict.fromkeys(str(p.get(f) or '') for p in items.values() for f in FIELDS));needed=[x for x in needed if x]
    cache_path=folder/'field-cache.npy'
    if cache_path.exists() and (folder/'field-texts.json').exists() and json.loads((folder/'field-texts.json').read_text())==needed:
        values=np.load(cache_path)
    else:
        values=encoder.encode(needed);np.save(cache_path,values);write_json(folder/'field-texts.json',needed)
    fields.cache.update(zip(needed,values));fields.encoded_texts=len(needed)
    for a,p in items.items():fields.update(a,p)
    field_initial=time.perf_counter()-started;field_matrix=np.stack([fields.vector(a) for a in ids])
    base=VectorIndex(ARTIFACTS/'vectors/document',encoder);document=np.stack([base.base[base.positions[a]] for a in ids])
    sums=defaultdict(lambda:np.zeros(384,dtype='float32'));counts=defaultdict(int)
    categories={a:tuple(items[a].get('categories') or []) for a in ids}
    for a,v in zip(ids,document):sums[categories[a]]+=v;counts[categories[a]]+=1
    def centroid(c):
        v=sums[c]/max(1,counts[c]);return v/max(float(np.linalg.norm(v)),1e-9)
    centroid_matrix=np.stack([centroid(categories[a]) for a in ids])
    queries=[r['opening']+' '+' '.join(r['answers'][:2]) for r in dev];q=encoder.encode(queries);results=[]
    for row,vector in zip(dev,q):
        for variant,score in [('fixed_document',document@vector),('field_composition',field_matrix@vector),('category_statistic',.9*(document@vector)+.1*(centroid_matrix@vector))]:
            order=np.argsort(-score,kind='stable');rank=next((i+1 for i,index in enumerate(order) if ids[index]==row['target']),1001)
            results.append({'sample_id':row['sample_id'],'group':row['group'],'variant':variant,'rank':rank,'hit10':rank<=10,'recall100':rank<=100})
    changes=[]
    for a in ids[:100]:
        old=items[a];changed={**old,'features':[]};before=fields.encoded_texts;started=time.perf_counter();fields.update(a,changed)
        newvector=encoder.encode([text(changed)])[0];i=ids.index(a);c=categories[a];sums[c]-=document[i];sums[c]+=newvector
        expected=np.sum([fields.cache[str(changed.get(f) or '')] for f in FIELDS if str(changed.get(f) or '')],axis=0)
        expected/=max(float(np.linalg.norm(expected)),1e-9)
        changes.append({'asin':a,'seconds':time.perf_counter()-started,'field_encodes':fields.encoded_texts-before,'document_encodes':1,
                        'field_delta_matches_recomposition':bool(np.allclose(fields.vector(a),expected,atol=1e-5)),'centroid_count_unchanged':counts[c]})
    before=fields.encoded_texts
    for a in ids[:20]:fields.update(a,None)
    delete_encodes=fields.encoded_texts-before;base.close()
    write_json(folder/'result.json',{'manifest':manifest({'subset_size':1000,'query_count':len(dev),'seed':20260910},[folder/'shared-products.jsonl']),
        'scope':'Shared 1000-product development probe, not full-catalog reachability evidence; metadata withdrawal is experimental',
        'field_initial_seconds':field_initial,'field_unique_text_encodes':len(needed),'quality':results,'changes':changes,'deletion_encodes':delete_encodes})
    print('Representation probe complete',len(results),'quality rows',flush=True)

if __name__=='__main__':run()
