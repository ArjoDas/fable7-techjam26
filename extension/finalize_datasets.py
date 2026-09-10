"""Freeze answer exposure before final comparisons; retain original generated rows."""
from pathlib import Path
from extension.common import ARTIFACTS,read_jsonl,write_jsonl,write_json,manifest
from extension.datasets import Shopper


def run():
    folder=ARTIFACTS/'datasets/canonical';folder.mkdir(parents=True,exist_ok=True);inputs=[];counts={};pairs=[];all_ids=set()
    for split,n in [('train',1600),('dev',800),('test',800)]:
        source=ARTIFACTS/f'datasets/{split}.jsonl';rows=sorted(read_jsonl(source),key=lambda r:r['sample_id']);inputs.append(source)
        if len(rows)!=n or len({r['target'] for r in rows})!=n:raise RuntimeError('Incomplete or duplicate split: '+split)
        if all_ids & {r['target'] for r in rows}:raise RuntimeError('Split overlap')
        all_ids.update(r['target'] for r in rows);fixed=[];adjustments=0
        for row in rows:
            row=dict(row);answer=row['answers'][0]
            if answer.casefold() not in row['opening'].casefold():
                row['opening']+=' '+answer;row['opening_adjustment']='Expose the already generated first-fact answer explicitly';adjustments+=1
            else:row['opening_adjustment']=None
            row['generation_config']=row.get('generation_config',{'schema_version':1,'legacy_seed_rule':'20260910 + sum(ord(sample_id))','max_tokens':800})
            fixed.append(row)
            for protocol in (False,True):
                shopper=Shopper(row,protocol=protocol,replay=True)
                pairs.append({'sample_id':row['sample_id'],'split':split,'target':row['target'],'conversation':'protocol' if protocol else 'natural','turns':[shopper.message(t,'other') for t in range(1,6)]})
        write_jsonl(folder/f'{split}.jsonl',fixed);counts[split]={'tasks':len(fixed),'first_fact_exposure_adjustments':adjustments}
    write_jsonl(folder/'paired-fixed-transcripts.jsonl',pairs)
    write_json(folder/'manifest.json',{'manifest':manifest({'rule':'Append only the already generated first answer if absent from opening; never add titles or new evidence'},inputs),'counts':counts,'paired_transcripts':len(pairs),'split_disjoint':True})

if __name__=='__main__':run()
