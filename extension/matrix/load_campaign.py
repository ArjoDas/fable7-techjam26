"""Qualify the chosen matrix route using the existing isolated HTTP load harness."""
import json
from evaluator import local_evaluator as official
from extension.matrix.common import *
from extension.matrix.events import decode,render

def prepare(variant,limit):
    from extension.catalog import Catalog
    from extension.matrix.growth import OrderedCatalog
    from extension.index import save_agent
    import sqlite3
    from extension.factory import create
    source=OrderedCatalog(HOME/'published/expanded-60000');folder=HOME/'serving-store'
    try:
        if not (folder/'catalog.sqlite').exists():
            folder.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(folder/'catalog.sqlite')
            try:source.db.backup(db)
            finally:db.close()
            save_agent(source.agent,folder/f'snapshot-{source.version}')
        store=Catalog(folder)
        if store.products!=source.products or store.version!=source.version:store.close();raise RuntimeError('Serving store changed from selected catalog snapshot')
    finally:source.close()
    agent=create(store,variant);bank=json.loads((HOME/'paraphrases/bank.json').read_text(encoding='utf-8'))
    rows=sorted(read_jsonl(HOME/'prepared/dev.jsonl'),key=lambda r:stable(r['sample_id']))[:limit];workload=[]
    try:
        for row in rows:
            target=row['ground_truth']['parent_asin']
            for level in ('constrained','wording','semantic'):
                sid=row['sample_id']+level;agent.reset(sid,row['user_profile']);disclosed=set();boundary=False;changed=row['scenario_type']!='intent_override'
                canonical=official.initial_message(row,official.coarse_category(store.products[target].get('categories',[])),disclosed);turns=[]
                for turn in range(1,6):
                    text,_=render(decode(canonical),level,row['sample_id'],SEEDS[0],'dev',bank);response=agent.respond(sid,text,turn,10);turns.append({'message':text,'expected':response['recommendations']})
                    override=row.get('behavior',{}).get('override') or {}
                    if not changed and turn+1==int(override.get('turn',3)):
                        changed=True;canonical=override['message'];disclosed.add(override['new_value'])
                    else:canonical,boundary=official.customer_reply(row,'other',disclosed,boundary)
                workload.append({'sample_id':row['sample_id'],'profile':row['user_profile'],'target':target,'family':level,'turns':turns});agent.close(sid)
        path=ARTIFACTS/f'load/workload-{variant}.jsonl';write_jsonl(path,workload);write_json(path.with_suffix('.manifest.json'),manifest({'matrix_variant':variant},[HOME/'prepared/dev.jsonl',HOME/'paraphrases/bank.json']))
    finally:
        if agent.vectors:agent.vectors.close()
        store.close()

def main():
    from extension.load_campaign import run
    selection=json.loads((HOME/'selection.json').read_text(encoding='utf-8'));scores={v:[] for v in selection['finalists']}
    for path in (HOME/'quality').glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'));c=d['manifest']['config']
        if c['label']=='full-dev' and c['variant'] in scores:scores[c['variant']].append(d['aggregate']['hit10_by_turn5'])
    chosen=max(scores,key=lambda v:(sum(scores[v])/len(scores[v]),v=='rules'));variant='matrix-'+chosen
    write_json(HOME/'serving-selection.json',{'variant':variant,'development_scores':scores,'sealed_results_not_used_for_selection':True})
    run(variant,True)
    result=json.loads((ARTIFACTS/'load/final-confirmation.json').read_text(encoding='utf-8'));write_json(HOME/'load-confirmation.json',result)

if __name__=='__main__':main()
