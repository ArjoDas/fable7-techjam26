"""Frozen encoder with persisted base vectors, changed-item deltas, and tombstones."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from extension.common import ARTIFACTS, MODEL_CACHE, ROOT, manifest, read_jsonl, write_json, sha256

FIELDS=('title','categories','features','details')


def text(product):return ' '.join(str(product.get(f) or '') for f in FIELDS)
def text_hash(value):return hashlib.sha256(value.encode()).hexdigest()


class VectorIndex:
    def __init__(self,directory,encoder=None,state_name='document'):
        self.state_name=state_name
        self.directory=Path(directory);self.encoder=encoder;self.encoded_texts=0
        self.meta=json.loads((self.directory/'base.json').read_text(encoding='utf-8'))
        self.ids=self.meta['ids'];self.positions={a:i for i,a in enumerate(self.ids)}
        self.base=np.load(self.directory/'base.npy',mmap_mode='r');self.delta={};self.tombstones=set();self.hashes=dict(self.meta['text_hashes'])
        self.version=-1;self.query_cache={};self.state_directory=self.directory;self.catalog_identity=None
        pointer=self.directory/'current.json'
        if pointer.exists():
            state=json.loads(pointer.read_text());data=json.loads((self.directory/state['metadata']).read_text())
            array=np.load(self.directory/state['vectors'])
            self.delta={a:array[i] for i,a in enumerate(data['ids'])};self.tombstones=set(data['tombstones']);self.hashes=data['hashes'];self.version=data['version']

    def _encoder(self):
        if self.encoder is None:
            from extension.models import Embeddings
            self.encoder=Embeddings(fp32=True)
        return self.encoder

    def sync(self,catalog):
        identity=str(catalog.directory.resolve())
        if self.catalog_identity!=identity:
            self.catalog_identity=identity;self.version=-1;self.delta={};self.tombstones=set();self.hashes=dict(self.meta['text_hashes']);self.query_cache.clear()
            self.state_directory=catalog.directory/('vector-state-'+self.state_name);self.state_directory.mkdir(parents=True,exist_ok=True)
            pointer=self.state_directory/'current.json'
            if pointer.exists():
                state=json.loads(pointer.read_text());data=json.loads((self.state_directory/state['metadata']).read_text())
                array=np.load(self.state_directory/state['vectors'])
                self.delta={a:array[i] for i,a in enumerate(data['ids'])};self.tombstones=set(data['tombstones']);self.hashes=data['hashes'];self.version=data['version']
        if self.version==catalog.version:return
        if self.version<0:
            affected=set(catalog.products)|set(self.ids)|set(self.delta)
        else:
            affected=set()
            for payload, in catalog.db.execute('SELECT events FROM events WHERE version>? AND version<=?',(self.version,catalog.version)):
                affected.update(json.loads(payload)['changed'])
        changed=[]
        for a in affected:
            product=catalog.products.get(a)
            if product is None or not product.get('available',True):self.tombstones.add(a)
            else:
                self.tombstones.discard(a)
                if self.hashes.get(a)!=text_hash(text(product)):changed.append(a)
        if changed:
            values=self._encoder().encode([text(catalog.products[a]) for a in changed]);self.encoded_texts+=len(changed)
            for a,v in zip(changed,values):self.delta[a]=v;self.hashes[a]=text_hash(text(catalog.products[a]))
        self.version=catalog.version
        self.query_cache.clear();self.persist()

    def persist(self):
        ids=sorted(self.delta);stem=f'delta-{self.version}'
        temp=self.state_directory/(stem+'.npy.tmp')
        with temp.open('wb') as stream:np.save(stream,np.stack([self.delta[a] for a in ids]) if ids else np.empty((0,self.base.shape[1]),dtype='float32'))
        temp.replace(self.state_directory/(stem+'.npy'))
        write_json(self.state_directory/(stem+'.json'),{'ids':ids,'tombstones':sorted(self.tombstones),'hashes':self.hashes,'version':self.version})
        write_json(self.state_directory/'current.json',{'metadata':stem+'.json','vectors':stem+'.npy'})

    def search(self,query,k=100,catalog=None):
        if catalog:self.sync(catalog)
        key=(query,k,self.version)
        if key in self.query_cache:return self.query_cache[key]
        vector=self._encoder().encode([query])[0]
        scores=self.base@vector
        excluded=self.tombstones|set(self.delta)
        for a in excluded:
            if a in self.positions:scores[self.positions[a]]=-np.inf
        n=min(k,len(scores));indices=np.argpartition(scores,-n)[-n:] if n else []
        ranked=[(float(scores[i]),self.ids[i]) for i in indices if np.isfinite(scores[i])]
        ranked.extend((float(v@vector),a) for a,v in self.delta.items() if a not in self.tombstones)
        result=[a for _,a in sorted(ranked,key=lambda x:(-x[0],x[1]))[:k]]
        if len(self.query_cache)>=2048:self.query_cache.clear()
        self.query_cache[key]=result;return result

    def compact(self,destination):
        destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
        ids=sorted((set(self.ids)|set(self.delta))-self.tombstones)
        values=np.stack([self.delta[a] if a in self.delta else self.base[self.positions[a]] for a in ids])
        np.save(destination/'base.npy',values)
        write_json(destination/'base.json',{'ids':ids,'text_hashes':{a:self.hashes[a] for a in ids},'encoder_revision':self.meta['encoder_revision'],'compaction_encoded_texts':0})

    def close(self):
        if getattr(self.base,'_mmap',None) is not None:self.base._mmap.close()


class FieldVectors:
    """A distinct field-composed representation; no claim of document-encoder equivalence."""
    def __init__(self,encoder):self.encoder=encoder;self.cache={};self.items={};self.sums={};self.encoded_texts=0
    def update(self,asin,product):
        if product is None:
            self.items.pop(asin,None);self.sums.pop(asin,None);return
        fields={f:str(product.get(f) or '') for f in FIELDS}
        needed=list(dict.fromkeys(v for v in fields.values() if v and v not in self.cache))
        if needed:
            self.cache.update(zip(needed,self.encoder.encode(needed)));self.encoded_texts+=len(needed)
        previous=self.items.get(asin,{})
        total=self.sums.get(asin,np.zeros(384,dtype='float32')).copy()
        for f,value in previous.items():
            if value and fields.get(f)!=value:total-=self.cache[value]
        for f,value in fields.items():
            if value and previous.get(f)!=value:total+=self.cache[value]
        self.items[asin]=fields;self.sums[asin]=total
    def vector(self,asin):
        value=self.sums[asin];return value/max(float(np.linalg.norm(value)),1e-9)


def prepare(gpu=False):
    from extension.models import Embeddings
    directory=ARTIFACTS/'vectors/document';directory.mkdir(parents=True,exist_ok=True)
    products=read_jsonl(ARTIFACTS/'catalog/catalog-60000.jsonl')
    old_ids=json.loads((MODEL_CACHE/'catalog_embedding_ids.json').read_text())
    assert [p['parent_asin'] for p in products[:50000]]==old_ids
    old_manifest=json.loads((MODEL_CACHE/'embeddings_manifest.json').read_text())
    assert sha256(ROOT/'data/catalog.jsonl') in old_manifest['inputs'].values()
    old=np.load(MODEL_CACHE/'catalog_embeddings.npy',mmap_mode='r');model=Embeddings(gpu=gpu,fp32=True)
    parts=[]
    for start in range(50000,len(products),128):
        path=directory/f'part-{start}.npy'
        if not path.exists():
            array=model.encode([text(p) for p in products[start:start+128]])
            with path.with_suffix('.tmp').open('wb') as stream:np.save(stream,array)
            path.with_suffix('.tmp').replace(path)
        parts.append(np.load(path));print('Encoded new products',min(start+128,len(products))-50000,'/ 10000',flush=True)
    np.save(directory/'base.npy',np.concatenate([old,*parts]))
    write_json(directory/'base.json',{'ids':[p['parent_asin'] for p in products],
        'text_hashes':{p['parent_asin']:text_hash(text(p)) for p in products},
        'encoder_revision':'1110a243fdf4706b3f48f1d95db1a4f5529b4d41','reused_original_vectors':50000,'newly_encoded_products':10000})
    write_json(directory/'manifest.json',manifest({'gpu':gpu,'shape':[60000,384]},[ARTIFACTS/'catalog/catalog-60000.jsonl',MODEL_CACHE/'embeddings_manifest.json']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--gpu',action='store_true');args=parser.parse_args();prepare(args.gpu)
