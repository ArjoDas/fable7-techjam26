"""Explicit component and release decisions based on completed measurements."""
import json
from collections import defaultdict
from extension.matrix.common import *

def main():
    decisions=[]
    for path in (HOME/'growth').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'));p=d['parity'];passed=not p['conversation_mismatches'] and all(p[k] for k in ('views_equal','cards_equal','prefixes_equal'))
        decisions.append({'alternative':path.stem,'decision':'retain' if passed else 'reject','scope':'Catalog-index component','reason':'Independent full-rebuild parity at this checkpoint','passed':passed})
    for path in (HOME/'adjustment').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'));decisions.append({'alternative':'batch-residual-'+path.stem,'decision':d['outcome'],'scope':'Separate development adjustment; main weights frozen'})
    results=defaultdict(list)
    for path in (HOME/'quality').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config']
        if c['label']=='sealed' and not c['replay'] and c['level']!='constrained':
            for group,metrics in d['by_group'].items():results[(c['schedule'],c['size'],c['variant'],c['level'],group)].append(metrics)
    gates=[]
    for key,rows in results.items():
        hit=sum(r['hit10_by_turn5'] for r in rows)/len(rows);recall=sum(r['recall100_by_turn5'] for r in rows)/len(rows)
        gates.append({'schedule':key[0],'size':key[1],'variant':key[2],'level':key[3],'group':key[4],'hit10_by_turn5':hit,'recall100_by_turn5':recall,'passed':len(rows)==3 and hit>=.9 and recall>=.95})
    pending=[name for name in ('paired-sealed.json','load-confirmation.json','official-regression.json','correctness/result.json') if not (HOME/name).exists()]
    if not pending:
        serving=json.loads((HOME/'serving-selection.json').read_text(encoding='utf-8'))['variant'].removeprefix('matrix-')
        relevant=[g for g in gates if g['variant']==serving];latency=json.loads((HOME/'load-confirmation.json').read_text(encoding='utf-8'))['passed']
        official=all(r['passed'] for r in json.loads((HOME/'official-regression.json').read_text(encoding='utf-8'))['results'])
        paired=[r for r in json.loads((HOME/'paired-sealed.json').read_text(encoding='utf-8'))['results'] if r['variant']==serving and r['group']=='all']
        correctness=json.loads((HOME/'correctness/result.json').read_text(encoding='utf-8'))['passed']
        passed=bool(relevant) and all(g['passed'] for g in relevant) and latency and official and correctness and bool(paired) and all(r['ci95'][0]>0 for r in paired)
        decisions.append({'alternative':serving,'decision':'retain' if passed else 'reject','scope':'Combined serving release','quality_passed':all(g['passed'] for g in relevant),'latency_passed':latency,'official_passed':official,'positive_paired_lower_bound':bool(paired) and all(r['ci95'][0]>0 for r in paired)})
    write_json(HOME/'outcomes.json',{'manifest':manifest({}),'decisions':decisions,'quality_gates':gates,'pending_release_evidence':pending})

if __name__=='__main__':main()
