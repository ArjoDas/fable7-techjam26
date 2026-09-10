"""Paired development comparisons for the semantic and state-scope ablations."""
import json
import numpy as np
from extension.common import ARTIFACTS,write_json,manifest


def main():
    baseline=ARTIFACTS/'quality/dev-tinybert-lexical-natural-interactive-semantic-screen.json';reference=json.loads(baseline.read_text(encoding='utf-8'));ref={r['sample_id']:r for r in reference['sessions']};results=[];rng=np.random.default_rng(20260910)
    paths=sorted((ARTIFACTS/'quality').glob('*semantic-screen.json'))+sorted((ARTIFACTS/'quality').glob('*state-scope-screen.json'))
    for path in paths:
        data=json.loads(path.read_text(encoding='utf-8'));rows=data['sessions']
        if {r['sample_id'] for r in rows}!=set(ref):continue
        delta=np.array([int(r['hit'])-int(ref[r['sample_id']]['hit']) for r in rows]);boot=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(10000)])
        results.append({'variant':data['manifest']['config']['variant'],'input_file':str(path),'hit10':data['aggregate']['hit_rate_at_10'],
            'recall100':data['aggregate']['recall100_any_turn'],'paired_gain':float(delta.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist(),
            'parser_calls':sum(t['trace'].get('model_calls',0) for r in rows for t in r['transcript']),
            'parser_failures':sum(bool(t['trace'].get('fallback_reason')) for r in rows for t in r['transcript']),
            'by_group':data['by_group'],'latency':data['aggregate']['response_latency']})
    write_json(ARTIFACTS/'rag/development-comparison.json',{'manifest':manifest({'seed':20260910},[baseline]),'comparisons':results,
        'interpretation':'Exploratory development, not sealed confirmation. State-scope variants change both retrieval configuration and constraint handling; compare corrected lexical against corrected passage variants to isolate embedding benefit.'})

if __name__=='__main__':main()
