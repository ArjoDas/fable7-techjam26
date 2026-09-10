"""Incremental product-passage embeddings with a fixed MiniLM encoder."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import numpy as np
from extension.common import ARTIFACTS,read_jsonl,write_json,manifest


def passages(product):
    category=' > '.join(map(str,product.get('categories') or []));title=str(product.get('title') or '')
    prefix=(category+'. '+title)[:400]
    facts=[str(v) for v in product.get('features') or []]
    facts += [str(k)+': '+str(v) for k,v in (product.get('details') or {}).items()]
    description=product.get('description') or []
    if isinstance(description,str):description=[description]
    facts+=list(map(str,description))
    chunks=[prefix];current=[];length=0
    for fact in facts:
        for offset in range(0,len(fact),500):
            piece=fact[offset:offset+500]
            if current and length+len(piece)>650:
                chunks.append(prefix+'\n'+' '.join(current));current=[];length=0
            current.append(piece);length+=len(piece)
    if current:chunks.append(prefix+'\n'+' '.join(current))
    # Explicitly bounded preprocessing: even very long listings cannot monopolize
    # inference. Coverage and this cap are recorded in the experiment manifest.
    return list(dict.fromkeys(chunks))[:6]


def key(text):return hashlib.sha256(text.encode()).hexdigest()


class PassageIndex:
    def __init__(self,catalog,encoder=None,namespace='default',use_base_cache=True,defer_sync=False):
        from extension.models import Embeddings
        self.catalog=catalog;self.encoder=encoder;self.version=-1;self.encoded_texts=0;self.cache={}
        folder=catalog.directory/('passages-'+namespace);folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(folder/'vectors.sqlite');self.db.execute('CREATE TABLE IF NOT EXISTS vectors(hash TEXT PRIMARY KEY,vector BLOB NOT NULL)')
        base=ARTIFACTS/'vectors/passages/cache.sqlite'
        self.base=sqlite3.connect(f'file:{base.as_posix()}?mode=ro',uri=True) if use_base_cache and base.exists() else None
        self.product_vectors={};self.product_hashes={};self.delta={}
        if not defer_sync:self.sync(catalog)
    def _encode(self,texts):
        if self.encoder is None:
            from extension.models import Embeddings
            self.encoder=Embeddings(fp32=True)
        return self.encoder.encode(texts)
    def vectors(self,texts):
        result={};missing=[]
        for text in texts:
            h=key(text);row=self.db.execute('SELECT vector FROM vectors WHERE hash=?',(h,)).fetchone()
            if row is None and self.base:row=self.base.execute('SELECT vector FROM vectors WHERE hash=?',(h,)).fetchone()
            if row:result[h]=np.frombuffer(row[0],dtype='float32')
            else:missing.append(text)
        missing=list(dict.fromkeys(missing))
        if missing:
            values=self._encode(missing);self.encoded_texts+=len(missing)
            with self.db:
                for text,v in zip(missing,values):self.db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?)',(key(text),v.astype('float32').tobytes()));result[key(text)]=v
        return np.stack([result[key(t)] for t in texts])
    def sync(self,catalog):
        if self.version==catalog.version:return
        initializing=self.version<0
        if initializing:affected=set(catalog.products)
        else:
            affected=set()
            for payload, in catalog.db.execute('SELECT events FROM events WHERE version>?',(self.version,)):affected.update(json.loads(payload)['changed'])
        for a in affected:
            product=catalog.products.get(a)
            if product is None or not product.get('available',True):
                self.product_vectors.pop(a,None);self.product_hashes.pop(a,None)
            else:
                texts=passages(product);hashes=tuple(map(key,texts))
                if self.product_hashes.get(a)!=hashes:self.product_vectors[a]=self.vectors(texts);self.product_hashes[a]=hashes
            if not initializing:
                position=self.base_positions.get(a)
                reusable=a in self.product_hashes and self.base_hashes.get(a)==self.product_hashes[a]
                if position is not None:self.base_active[position]=reusable
                if a in self.product_vectors and not reusable:self.delta[a]=self.product_vectors[a]
                else:self.delta.pop(a,None)
        self.ids=sorted(self.product_vectors)
        if initializing:self.compact()
        else:self._pack_delta()
        self.version=catalog.version;self.cache.clear()

    @staticmethod
    def _pack(ids,vectors):
        owners=np.concatenate([np.full(len(vectors[a]),i,dtype='int32') for i,a in enumerate(ids)]) if ids else np.array([],dtype='int32')
        matrix=np.concatenate([vectors[a] for a in ids]) if ids else np.empty((0,384),dtype='float32')
        return owners,matrix

    def _pack_delta(self):
        self.delta_ids=sorted(self.delta);self.delta_owners,self.delta_matrix=self._pack(self.delta_ids,self.delta)

    def compact(self):
        """Merge stored vectors without invoking the encoder; never per-event."""
        self.base_ids=sorted(self.product_vectors);self.base_positions={a:i for i,a in enumerate(self.base_ids)}
        self.base_hashes=dict(self.product_hashes);self.base_active=np.ones(len(self.base_ids),dtype=bool)
        self.owners,self.matrix=self._pack(self.base_ids,self.product_vectors)
        self.delta={};self._pack_delta();self.cache.clear()
    def search(self,query,k=100,catalog=None):
        self.sync(catalog or self.catalog)
        cachekey=(query,k,self.version)
        if cachekey in self.cache:return self.cache[cachekey]
        query_vector=self._encode([query])[0];base_scores=np.full(len(self.base_ids),-np.inf,dtype='float32')
        np.maximum.at(base_scores,self.owners,self.matrix@query_vector)
        values={a:float(base_scores[i]) for i,a in enumerate(self.base_ids) if self.base_active[i]}
        if self.delta_ids:
            delta_scores=np.full(len(self.delta_ids),-np.inf,dtype='float32')
            np.maximum.at(delta_scores,self.delta_owners,self.delta_matrix@query_vector)
            values.update(zip(self.delta_ids,map(float,delta_scores)))
        scores=np.array([values[a] for a in self.ids],dtype='float32')
        indices=np.argsort(-scores,kind='stable')[:k];result=[self.ids[i] for i in indices]
        if len(self.cache)>=512:self.cache.clear()
        self.cache[cachekey]=result;return result
    def close(self):
        self.db.close()
        if self.base:self.base.close()


def prepare(gpu=False,limit=None):
    from extension.models import Embeddings
    source=ARTIFACTS/'catalog/catalog-60000.jsonl';products=read_jsonl(source);products=products[:limit] if limit else products
    folder=ARTIFACTS/'vectors/passages';folder.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(folder/'cache.sqlite');db.execute('CREATE TABLE IF NOT EXISTS vectors(hash TEXT PRIMARY KEY,vector BLOB NOT NULL)')
    existing={r[0] for r in db.execute('SELECT hash FROM vectors')};texts={key(t):t for p in products for t in passages(p)};missing=[t for h,t in texts.items() if h not in existing]
    model=Embeddings(gpu=gpu,fp32=True);started=time.perf_counter()
    for start in range(0,len(missing),128):
        batch=missing[start:start+128];values=model.encode(batch)
        with db:db.executemany('INSERT OR IGNORE INTO vectors VALUES (?,?)',[(key(t),v.tobytes()) for t,v in zip(batch,values)])
        if start%2048==0:print('Passages encoded',start+len(batch),'/',len(missing),flush=True)
    write_json(folder/'manifest.json',{'manifest':manifest({'gpu':gpu,'limit':limit,'max_passages_per_product':6,'encoder':'fixed MiniLM'},[source]),'products':len(products),'unique_passages':len(texts),'newly_encoded':len(missing),'seconds':time.perf_counter()-started});db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--limit',type=int);a=p.parse_args();prepare(a.gpu,a.limit)
