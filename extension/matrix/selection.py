"""Development-only selection and product-clustered paired confidence intervals."""
import json
import numpy as np
from collections import defaultdict
from extension.matrix.common import *

def choose_converter(label='screen'):
    scores=defaultdict(list)
    for path in (HOME/'quality').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'));c=data['manifest']['config']
        if c['split']=='dev' and c['label']==label and c['variant'] in ('rules','qwen') and c['level']!='constrained':scores[c['variant']].append(data['aggregate']['hit10_by_turn5'])
    if set(scores)!={'rules','qwen'}:raise RuntimeError('Both converter screens are required')
    return max(scores,key=lambda v:(sum(scores[v])/len(scores[v]),v=='rules'))

def freeze(converter,threshold):
    path=HOME/'selection.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    inputs=[HOME/f'prepared/{s}.jsonl' for s in ('train','dev','test')]+[HOME/'prepared/membership.json',HOME/'paraphrases/bank.json',HOME/'paraphrases/audit.json']
    files=[]
    for p in (HOME/'quality').glob('*.json'):
        d=json.loads(p.read_text(encoding='utf-8'))
        if d['manifest']['config']['label']=='full-dev':files.append(p)
    if not files:raise RuntimeError('Missing full development results')
    result={'manifest':manifest({'policy':'Best screened converter plus direct semantic comparator; no sealed tuning'},inputs+files),'finalists':[converter,'semantic'],'threshold':threshold,
        'gates':{'hit10_by_turn5':.9,'recall100_by_turn5':.95,'latency_p99_ms':2000,'response_rps':5,'failure_rate':.01}}
    write_json(path,result);return result

def paired():
    rows={};records=[];rng=np.random.default_rng(SEEDS[0])
    for path in (HOME/'quality').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config']
        if c['label']=='sealed' and c['level']!='constrained' and not c['replay']:rows[(c['schedule'],c['size'],c['level'],c['seed'],c['variant'])]=d
    selection=json.loads((HOME/'selection.json').read_text(encoding='utf-8'))
    for schedule,size,level in sorted({k[:3] for k in rows}):
        for variant in selection['finalists']:
            for group in ('all','original','new'):
                clusters=defaultdict(list)
                for seed in SEEDS:
                    base=rows[(schedule,size,level,seed,'main')];candidate=rows[(schedule,size,level,seed,variant)]
                    reference={r['sample_id']:r for r in base['sessions']}
                    for row in candidate['sessions']:
                        if group!='all' and ('original' if row['group']=='original' else 'new')!=group:continue
                        previous=reference[row['sample_id']];clusters[row['sample_id']].append(int(row['hit'] and row['first_hit_turn']<=5)-int(previous['hit'] and previous['first_hit_turn']<=5))
                if not clusters:continue
                delta=np.array([np.mean(v) for v in clusters.values()]);boot=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(10000)])
                records.append({'schedule':schedule,'size':size,'level':level,'variant':variant,'group':group,'product_clusters':len(delta),'paired_gain':float(delta.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist()})
    write_json(HOME/'paired-sealed.json',{'manifest':manifest({}), 'results':records,'bootstrap_unit':'Product task, aggregating all three paraphrase seeds before resampling'})
