"""Explicit measured decisions without converting unfinished experiments into failures."""
import json
from extension.common import ARTIFACTS,write_json,manifest


def read(path):return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def main():
    rows=[]
    parity=read(ARTIFACTS/'updates/run-1/parity-deterministic.json');updates=read(ARTIFACTS/'updates/run-1/result.json')
    if parity and updates:
        passed=parity['ordered_mismatches']==0 and updates['restart_equal']
        rows.append({'alternative':'incremental lexical','decision':'retain' if passed else 'reject','reason':'Faster growth updates with deterministic rebuild parity and restart recovery' if passed else 'Correctness gate failed','scope':'Catalog engineering component, not combined serving release'})
        rows.append({'alternative':'full rebuild','decision':'retain','reason':'Independent correctness reference and recovery mechanism; observed growth cost exceeds incremental updates'})
    vectors=read(ARTIFACTS/'vectors/update-probe/result.json')
    if vectors:
        failed=any(r['encoded_documents'] for r in vectors['measurements'] if r['event'] in ('delete','reintroduce-identical-text','compaction'))
        rows.append({'alternative':'fixed encoder with document updates','decision':'reject' if failed else 'retain','reason':'Changed documents only; deletion/reintroduction/compaction must not re-encode unchanged text','scope':'Encoding efficiency; retrieval quality evaluated separately'})
    representation=read(ARTIFACTS/'representations/result.json')
    if representation:
        scores={v:sum(r['hit10'] for r in representation['quality'] if r['variant']==v)/sum(r['variant']==v for r in representation['quality']) for v in {r['variant'] for r in representation['quality']}}
        for alternative,variant in [('field-vector deltas','field_composition'),('catalog-statistic adaptation','category_statistic')]:
            rows.append({'alternative':alternative,'decision':'retain' if scores[variant]>scores['fixed_document'] else 'reject','reason':'Shared-subset HitRate@10 comparison against fixed document representation','quality':scores,'scope':'1000-product feasibility probe; not extrapolated to full catalog'})
    light=read(ARTIFACTS/'updates/lightrag-100/results.json')
    if light:rows.append({'alternative':'LightRAG','decision':'retain' if light['status']=='measured_pilot' else 'infeasible','reason':light['status'],'scope':'100-product pilot; promotion requires complete successful ingestion, deletion and reintroduction'})
    selection=read(ARTIFACTS/'selection/frozen.json')
    if selection:
        for candidate in selection['candidates']:
            rows.append({'alternative':candidate['variant'],'decision':'retain' if candidate['variant'] in selection['local_finalists'] else 'reject','reason':'Frozen development ranking','scope':'Experimental finalist, not a passed release gate'})
    write_json(ARTIFACTS/'outcomes.json',{'manifest':manifest({}),'decisions':rows,'incomplete_alternatives_are_not_assigned_outcomes':True})

if __name__=='__main__':main()
