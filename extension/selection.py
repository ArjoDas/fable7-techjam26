"""Freeze development-selected finalists, then perform paired sealed confirmation."""
import argparse
import json
import subprocess
import sys
import numpy as np
from extension.common import ARTIFACTS,ROOT,manifest,write_json,sha256,dataset_path


def freeze():
    folder=ARTIFACTS/'selection';path=folder/'frozen.json'
    if path.exists():raise RuntimeError('Selection already frozen; do not retune against sealed results')
    canonical=ARTIFACTS/'datasets/canonical/manifest.json'
    if not canonical.exists():raise RuntimeError('Complete and freeze the generated benchmark first')
    candidates=[]
    for variant in ('rules','hybrid','graph','tinybert','tinybert-100','tinybert-lexical','gated-tinybert','minilm-cross','learned','residual','rag','rag-passages','rag-local','rag-passages-local','corrected-lexical','rag-passages-corrected','rag-passages-local-corrected'):
        result=ARTIFACTS/f'quality/dev-{variant}-natural-interactive-canonical-dev.json'
        if not result.exists():raise RuntimeError('Missing full development comparison: '+variant)
        data=json.loads(result.read_text(encoding='utf-8'));quality=data['aggregate']['hit_rate_at_10'];latency=data['aggregate']['response_latency']['p99_ms']
        candidates.append({'variant':variant,'hit_rate':quality,'latency_ms':latency,'file':str(result),'sha256':sha256(result)})
    candidates.sort(key=lambda c:(-c['hit_rate'],c['latency_ms'],c['variant']))
    chosen=candidates[:2]
    write_json(path,{'manifest':manifest({'selection':'Top two full-development recovery rates, latency breaks ties; latency qualification is separate'},[canonical,*[dataset_path(s) for s in ('train','dev','test')]]),
        'local_finalists':[c['variant'] for c in chosen],'api_finalists':[], 'candidates':candidates,
        'api_decision':'No API finalist selected without measured improvement over the best local route. Exploratory API results retained.',
        'quality_gates_unchanged':{'recall100':.95,'hit10':.90,'p99_ms':2000,'rps':5}})


def confirm():
    path=ARTIFACTS/'selection/frozen.json';selection=json.loads(path.read_text(encoding='utf-8'))
    current=manifest({})
    if current['artifact_provenance_hashes']!=selection['manifest']['artifact_provenance_hashes']:raise RuntimeError('Model artifacts changed after selection freeze')
    from pathlib import Path
    if any(sha256(Path(path))!=expected for path,expected in selection['manifest']['inputs'].items()):raise RuntimeError('Frozen dataset changed')
    if current['source_hashes']!=selection['manifest']['source_hashes']:raise RuntimeError('Serving/evaluation code changed after selection freeze')
    for variant in ['main',*selection['local_finalists'],*selection['api_finalists']]:
        for protocol in (False,True):
            args=[sys.executable,'-u','-m','extension.evaluate','--variant',variant,'--split','test','--label','sealed']
            if protocol:args.append('--protocol')
            subprocess.run(args,check=True)
        subprocess.run([sys.executable,'-u','-m','extension.evaluate','--variant',variant,'--split','test','--label','sealed','--replay'],check=True)
    baseline=json.loads((ARTIFACTS/'quality/test-main-natural-interactive-sealed.json').read_text(encoding='utf-8'))
    reference={r['sample_id']:r for r in baseline['sessions']};results=[];rng=np.random.default_rng(20260910)
    for variant in selection['local_finalists']:
        data=json.loads((ARTIFACTS/f'quality/test-{variant}-natural-interactive-sealed.json').read_text(encoding='utf-8'))
        for group in ('all','original','new'):
            rows=[r for r in data['sessions'] if group=='all' or (r['group']=='original')==(group=='original')]
            delta=np.array([int(r['hit'])-int(reference[r['sample_id']]['hit']) for r in rows]);boot=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(10000)])
            results.append({'variant':variant,'group':group,'tasks':len(rows),'paired_gain':float(delta.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist(),
                'hit10':sum(r['hit'] for r in rows)/len(rows),'recall100':sum(r['recall100'] for r in rows)/len(rows)})
    write_json(ARTIFACTS/'selection/sealed-results.json',{'manifest':manifest({},[path]),'paired_results':results})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','confirm']);a=p.parse_args();freeze() if a.action=='freeze' else confirm()
