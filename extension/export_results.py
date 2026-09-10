"""Export compact evidence for Git while retaining large raw artifacts locally."""
import json
from extension.common import ARTIFACTS,ROOT,write_json,sha256


def main():
    folder=ROOT/'extension/results';folder.mkdir(parents=True,exist_ok=True);index=[]
    paths=[*list((ARTIFACTS/'baselines').glob('*.json')),ARTIFACTS/'catalog/manifest.json',ARTIFACTS/'vectors/document/manifest.json',
        ARTIFACTS/'updates/run-1/result.json',ARTIFACTS/'updates/run-1/parity-deterministic.json',ARTIFACTS/'updates/batched/result.json',
        ARTIFACTS/'representations/result.json',ARTIFACTS/'vectors/update-probe/result.json',ARTIFACTS/'updates/lightrag-100/results.json',
        ARTIFACTS/'api/screen-screen-15.0.json',ARTIFACTS/'api/screen-screen-1.2.json',ARTIFACTS/'datasets/audit.json',ARTIFACTS/'datasets/semantic-audit.json',
        ARTIFACTS/'selection/frozen.json',ARTIFACTS/'selection/sealed-results.json',ARTIFACTS/'load/final-confirmation.json']
    paths+=list((ARTIFACTS/'quality').glob('*screen-v2.json'))
    paths+=list((ARTIFACTS/'quality').glob('*semantic-screen.json'))
    paths+=list((ARTIFACTS/'quality').glob('*state-scope-screen.json'))
    paths+=[ARTIFACTS/'vectors/passages/manifest.json',ARTIFACTS/'rag/unseen-update/result.json',ARTIFACTS/'rag/development-comparison.json']
    paths+=[ARTIFACTS/'rag/delta-store-1/result.json',ARTIFACTS/'datasets/canonical/manifest.json']
    for path in paths:
        if not path.exists():continue
        value=json.loads(path.read_text(encoding='utf-8'))
        compact={k:v for k,v in value.items() if k not in ('sessions','quality','changes','examples','model_usage','results','defects')}
        if 'quality' in value:
            compact['representation_quality']={name:{'tasks':len(rows),'hit10':sum(r['hit10'] for r in rows)/len(rows),'recall100':sum(r['recall100'] for r in rows)/len(rows)} for name in {r['variant'] for r in value['quality']} for rows in [[r for r in value['quality'] if r['variant']==name]]}
        if 'changes' in value:compact['change_count']=len(value['changes']);compact['field_delta_mismatches']=sum(not r['field_delta_matches_recomposition'] for r in value['changes'])
        name='-'.join(path.relative_to(ARTIFACTS).parts);destination=folder/name;write_json(destination,compact)
        index.append({'source':str(path.relative_to(ROOT)),'raw_sha256':sha256(path),'compact':str(destination.relative_to(ROOT))})
    write_json(folder/'index.json',index)

if __name__=='__main__':main()
