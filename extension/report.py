"""Evidence-backed compact report; pending experiments never receive invented outcomes."""
import json
from pathlib import Path
from extension.common import ARTIFACTS,ROOT,write_json,manifest


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def main():
    report=ROOT/'docs/extension-results.md';lines=['# Extension results','', 'This report separates observed measurements from incomplete release gates.','']
    public=read(ARTIFACTS/'baselines/public.json')
    if public:
        a=public['aggregate'];lines+=['## Official compatibility','',f"Public: HitRate@10 **{a['hit_rate_at_10']}**, MRR **{a['mrr']}**, MTTC **{a['mttc']}**, TechnicalScore **{a['recommended_technical_score']}**. Model calls: {public['model_calls']}.",'']
    updates=read(ARTIFACTS/'updates/run-1/result.json')
    if updates:
        lines+=['## Catalog growth','', '| Added total | Incremental batch | Full rebuild | Sampled ranking differences |','|---:|---:|---:|---:|']
        for stage in (1000,5000,10000):
            name=f'growth-{stage}';u=next(r for r in updates['updates'] if r['name']==name);p=next(r for r in updates['parity'] if r['name']==name)
            lines.append(f"| {stage:,} | {u['seconds']:.2f} s | {p['full_rebuild_seconds']:.2f} s | {p['ordered_mismatches']}/{p['queries']} |")
        lines+=['',f"Restart recovery: **{updates['restart_equal']}**. Duplicate events idempotent: **{updates['duplicate_idempotent']}**. Stale events rejected: **{updates['stale_rejected']}**.",'',
          'The first sustained unbatched stream fell behind at 10 and 100 events/s. Its backlog is retained. The original final comparison had three tied-order differences with identical candidate sets; deterministic extended-route ordering is checked separately.','']
    parity=read(ARTIFACTS/'updates/run-1/parity-deterministic.json')
    if parity:lines += [f"Deterministic extended lexical parity: **{parity['ordered_mismatches']} differences across {parity['queries']} queries**.",'']
    lines+=['## Exploratory development screen','', 'Fixed 120-task development subset. Accuracy screens ran alongside other work, so their latency is not production qualification. Early screens also preceded final simulator exposure fixes.','', '| Variant | HitRate@10 | Recall@100, any observed turn |','|---|---:|---:|']
    for p in sorted((ARTIFACTS/'quality').glob('*screen-v2.json')):
        data=read(p);a=data['aggregate'];name=data['manifest']['config']['variant'];lines.append(f"| {name} | {a['hit_rate_at_10']:.2%} | {a['recall100_any_turn']:.2%} |")
    api=read(ARTIFACTS/'api/screen-screen-1.2.json')
    if api:
        lines+=['','## API deadline screen','','Twelve requests per available provider/mode; exploratory, not a p99 claim. Unknown timeout charges retain their full budget reservations.','', '| Provider | Task | Calls | Failures |','|---|---|---:|---:|']
        for r in api['summary']:lines.append(f"| {r['provider']} | {r['mode']} | {r['calls']} | {sum(r['errors'].values())} |")
        from extension.providers import Ledger
        lines+=['',f"Current charged-or-reserved budget: **${Ledger().summary()['charged_or_reserved_usd']:.4f} / $10**. Gemini returned HTTP 404; no more expensive model was substituted.",'']
    light=read(ARTIFACTS/'updates/lightrag-100/results.json')
    lines+=['## Release status','']
    pending=[]
    for label,path in [('sealed generalization',ARTIFACTS/'selection/sealed-results.json'),('isolated load confirmation',ARTIFACTS/'load/final-confirmation.json'),('semantic generation audit',ARTIFACTS/'datasets/semantic-audit.json')]:
        if not path.exists():pending.append(label)
    if not light:pending.append('LightRAG pilot outcome')
    if light:lines.append('LightRAG pilot status: **'+light['status']+'**.')
    lines+=['Pending: '+', '.join(pending)+'.' if pending else 'All listed campaign reports are present; consult their explicit gate outcomes.',
        '', 'No claim is made that the combined quality, latency, and compatibility release gates have passed. Raw datasets, source records, traces, event streams, and measurements remain in `data/releases/extension-v1/`. Reproduction commands are in `extension/README.md`.','']
    report.write_text('\n'.join(lines),encoding='utf-8');write_json(ARTIFACTS/'report-status.json',{'manifest':manifest({}),'pending':pending,'report':str(report)})
    from extension.export_results import main as export
    export()
    print(report,flush=True)

if __name__=='__main__':main()
