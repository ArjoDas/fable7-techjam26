"""Bounded, reproducible sampling of real upstream Amazon metadata."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
import random
import urllib.request
from extension.common import ARTIFACTS, ROOT, manifest, read_jsonl, write_json, write_jsonl

SOURCES={'Clothing_Shoes_and_Jewelry':5000,'Electronics':2500,'Home_and_Kitchen':2500}


def normalize(raw, source):
    price=raw.get('price')
    try: price=float(price)
    except (ValueError,TypeError): price=None
    return {key:raw.get(key) for key in ('parent_asin','title','features','description','details','store','rating_number','average_rating')} | {
        'categories':raw.get('categories') or [raw.get('main_category') or source.replace('_',' ')],
        'price':price,'main_category':raw.get('main_category') or source.replace('_',' '),
        'available':True}


def fetch(source, count, excluded, scan):
    folder=ARTIFACTS/'sources'; output=folder/f'{source}.jsonl'
    if output.exists():
        rows=read_jsonl(output)
        if len(rows)==count:return rows
        raise RuntimeError('Refusing to overwrite partial retained source: '+str(output))
    url=f'https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories/meta_{source}.jsonl.gz'
    rng=random.Random(20260910+sum(map(ord,source))); selected=[]; seen=set(); eligible=0
    request=urllib.request.Request(url,headers={'User-Agent':'TechJam-extension-research/1.0'})
    with urllib.request.urlopen(request,timeout=90) as remote, gzip.GzipFile(fileobj=remote) as gz, io.TextIOWrapper(gz,encoding='utf-8') as stream:
        for line_number,line in enumerate(stream,1):
            raw=json.loads(line); asin=raw.get('parent_asin')
            if asin and asin not in excluded and asin not in seen and raw.get('features') and raw.get('title'):
                seen.add(asin);eligible+=1
                row={'product':normalize(raw,source),'raw':raw,'source_url':url,'source_line':line_number,
                     'source_record_sha256':hashlib.sha256(line.encode()).hexdigest(),'source_category':source}
                if len(selected)<count:selected.append(row)
                else:
                    at=rng.randrange(eligible)
                    if at<count:selected[at]=row
            if line_number%10000==0:print(source,'scanned',line_number,'eligible',eligible,flush=True)
            if line_number>=scan:break
    if len(selected)!=count:raise RuntimeError(f'Insufficient real products in {source}: {len(selected)}')
    selected.sort(key=lambda r:r['product']['parent_asin'])
    write_jsonl(output,selected)
    write_json(folder/f'{source}.manifest.json',{'manifest':manifest({'scan_limit':scan,'seed':20260910+sum(map(ord,source))}),
        'source_url':url,'scanned':line_number,'eligible':eligible,'retained':len(selected),
        'sampling':'Reservoir sample of bounded source prefix; requires features and title; not whole-Amazon representative'})
    return selected


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,default=50000);args=parser.parse_args()
    original=read_jsonl(ROOT/'data/catalog.jsonl');ids={r['parent_asin'] for r in original}
    assert len(original)==len(ids)==50000
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(fetch,k,n,ids,args.scan) for k,n in SOURCES.items()]
        groups=[f.result() for f in futures]
    rows=[r for group in groups for r in group]
    newids=[r['product']['parent_asin'] for r in rows]
    assert len(newids)==len(set(newids))==10000 and not ids.intersection(newids)
    # Interleave categories so all staged growth snapshots contain the new domains.
    ordered=[]
    for i in range(2500):ordered.extend([groups[0][2*i],groups[0][2*i+1],groups[1][i],groups[2][i]])
    write_jsonl(ARTIFACTS/'catalog/additions.jsonl',ordered)
    for n in (1000,5000,10000):write_jsonl(ARTIFACTS/f'catalog/catalog-{50000+n}.jsonl',original+[r['product'] for r in ordered[:n]])
    write_json(ARTIFACTS/'catalog/manifest.json',{'manifest':manifest({'additions':SOURCES},[ROOT/'data/catalog.jsonl',*[ARTIFACTS/f'sources/{s}.jsonl' for s in SOURCES]]),
        'original_count':50000,'new_count':10000,'total':60000,'fake_products':0})
    print('Verified 60,000 unique source-backed products',flush=True)


if __name__=='__main__':main()
