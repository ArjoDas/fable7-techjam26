"""Six-cell measured results with explicit pending gates and retained failures."""
import json
from extension.matrix.common import *

def main():
    from extension.matrix.outcomes import main as outcomes
    outcomes()
    lines=['# Query language × catalog growth','', 'Controlled evaluator-derived experiments. Results outside the public frozen-50k run are experimental.','',
        '## Official compatibility','']
    p=HOME/'official-regression.json'
    if p.exists():
        for row in json.loads(p.read_text(encoding='utf-8'))['results']:lines.append(f"- {row['variant']}: TechnicalScore {row['metrics']['recommended_technical_score']}, model calls {row['model_calls']}, passed {row['passed']}.")
    else:lines.append('Pending.')
    lines+=['','## Catalog checkpoints','','| Schedule | Products | Added | Update seconds | Rebuild seconds | Conversation mismatches |','|---|---:|---:|---:|---:|---:|']
    for path in sorted((HOME/'growth').glob('*.json')):
        d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config'];timing='unmeasured after interruption' if d['incremental_seconds'] is None else f"{d['incremental_seconds']:.3f}"
        optimized=HOME/f"optimized-growth/{c['schedule']}-{c['size']}/result.json"
        if optimized.exists():timing+=f" → {json.loads(optimized.read_text(encoding='utf-8'))['incremental_seconds']:.3f} optimized"
        lines.append(f"| {c['schedule']} | {c['size']} | {d['added']} | {timing} | {d['parity']['rebuild_seconds']:.3f} | {len(d['parity']['conversation_mismatches'])} |")
    lines+=['','Zero-addition rows describe initial checkpoints; their update column is not initial preprocessing time. Startup and clean-cache embedding work are recorded separately.','',
        '## Query comparisons','','| Catalog | Size | Language | Variant | Split / phase | Seed | Tasks | Hit10 by 5 | Recall100 by 5 | MRR | MTTC |','|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|']
    compact=[]
    for path in sorted((HOME/'quality').glob('*.json')):
        d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config'];a=d['aggregate'];compact.append({k:v for k,v in d.items() if k!='sessions'})
        lines.append(f"| {c['schedule']} | {c['size']} | {c['level']} | {c['variant']} | {c['split']} / {c['label']} | {c['seed']} | {a['sample_count']} | {a['hit10_by_turn5']:.2%} | {a['recall100_by_turn5']:.2%} | {a['mrr']:.4f} | {a['mttc']} |")
    lines+=['','## Interpretation and outstanding evidence','','Three seeds reuse product tasks and are not independent samples. Paired confidence intervals cluster by product. Semantic generation fallbacks and AI audit flags remain in the denominator. Existing broad-campaign results are historical, not measurements of this matrix.','']
    for name,path in [('Semantic paraphrase bank',HOME/'paraphrases/manifest.json'),('200-example equivalence audit',HOME/'paraphrases/audit.json'),('Frozen finalists',HOME/'selection.json'),('Sealed paired comparison',HOME/'paired-sealed.json'),('Load confirmation',HOME/'load-confirmation.json')]:lines.append(f"- {name}: {'recorded; inspect artifact gates' if path.exists() else 'pending'}.")
    examples=[]
    for path in sorted((HOME/'quality').glob('*rules-wording*screen-v2.json')):
        d=json.loads(path.read_text(encoding='utf-8'))
        for row in d['sessions']:
            for turn in row['turns']:
                if len(examples)<4 and turn['trace'].get('canonical_text'):examples.append({'input':turn['message'],'normalized':turn['trace']['canonical_text'],'expected_event':turn['event'],'conversion_event':turn['trace'].get('event')})
    if examples:
        lines+=['','## Retained translation examples','']
        for example in examples[:3]:lines+=['- Input: '+example['input'].replace('\n',' '),'  Normalized: '+example['normalized'].replace('\n',' ')]
        write_json(HOME/'translation-examples.json',examples)
    lines+=['','No combined quality/latency release claim is made without completed gate evidence.','', '![Query matrix](matrix-figures/quality-growth.png)','', '![Catalog growth cost](matrix-figures/update-growth.png)','']
    (ROOT/'docs/query-data-matrix.md').write_text('\n'.join(lines),encoding='utf-8');write_json(HOME/'compact-results.json',compact)
    write_json(ROOT/'extension/results/matrix-summary.json',{'quality':compact,'raw_artifact_root':str(HOME.relative_to(ROOT)),'datasets':json.loads((HOME/'prepared/manifest.json').read_text(encoding='utf-8')) if (HOME/'prepared/manifest.json').exists() else None})
    from extension.matrix.charts import main as charts
    charts()
    print(ROOT/'docs/query-data-matrix.md',flush=True)

if __name__=='__main__':main()
