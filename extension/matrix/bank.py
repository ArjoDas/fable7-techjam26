"""Offline semantic paraphrases: no generation during retrieval measurements."""
import argparse,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from evaluator.local_evaluator import coarse_category
from extension.matrix.common import *
from extension.models import LocalLLM

def validate(source,text):
    flags=[]
    if not isinstance(text,str) or not text.strip():return ['empty']
    if sorted(re.findall(r'\d+(?:\.\d+)?',source))!=sorted(re.findall(r'\d+(?:\.\d+)?',text)):flags.append('number_change')
    if re.findall(r'\bB[A-Z0-9]{9}\b',text):flags.append('identifier')
    if bool(re.search(r'\b(no|not|never|without)\b',source,re.I))!=bool(re.search(r'\b(no|not|never|without)\b',text,re.I)):flags.append('negation_change')
    if len(text)>max(100,len(source)*2):flags.append('excess_expansion')
    return flags

def generate(value):
    prompt=('Paraphrase only this shopping preference/category as three short customer phrases with exactly the same meaning. '
        'Do not add product facts, numbers, use cases, opinions or purchase intent. Preserve negation and all numbers. '
        'Return JSON {"paraphrases":[three strings]}. Text: '+json.dumps(value))
    raw='';usage={};error=None;alternatives=[]
    try:
        raw,usage=LocalLLM(timeout=30).complete(prompt,max_tokens=240,seed=int(stable(value)[:7],16),stop=['</think>','</s>'])
        parsed=json.loads(raw[raw.find('{'):raw.rfind('}')+1])['paraphrases']
        if not isinstance(parsed,list):raise ValueError('Expected list')
        alternatives=[{'text':t,'flags':validate(value,t)} for t in parsed[:3] if isinstance(t,str)]
    except Exception as exc:error=type(exc).__name__
    return {'source':value,'prompt':prompt,'raw':raw,'usage':usage,'alternatives':alternatives,'error':error}

def main(limit=None):
    prepared=HOME/'prepared';products={p['parent_asin']:p for p in read_jsonl(prepared/'ordered-products.jsonl')};values=set()
    for split in ('train','dev','test'):
        for r in read_jsonl(prepared/f'{split}.jsonl'):
            values.add(coarse_category(products[r['ground_truth']['parent_asin']].get('categories',[])))
            values.update(r['intent_card']['hard_constraints']);values.update(r['intent_card']['soft_preferences'])
    folder=HOME/'paraphrases';folder.mkdir(parents=True,exist_ok=True);path=folder/'generation.jsonl';existing=read_jsonl(path) if path.exists() else [];seen={r['source'] for r in existing}
    missing=sorted(values-seen);missing=missing[:limit] if limit else missing
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(generate,v) for v in missing]):
            row=future.result();existing.append(row)
            with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            if len(existing)%50==0:print('Semantic phrases',len(existing),'/',len(values),flush=True)
    accepted={r['source']:[a['text'] for a in r['alternatives'] if not a['flags']] for r in existing}
    write_json(folder/'bank.json',accepted)
    write_json(folder/'manifest.json',{'manifest':manifest({'offline':True,'limit':limit},[prepared/'manifest.json',path]),'required':len(values),'attempted':len(existing),'with_accepted_alternative':sum(bool(accepted.get(v)) for v in values),'complete':values<=set(accepted),'validation':'Structural checks only; semantic equivalence requires audit; missing alternatives fall back explicitly to literal values'})

def seal():
    """Revalidate retained generations without editing or discarding their raw output."""
    folder=HOME/'paraphrases';raw=folder/'generation.jsonl';records=read_jsonl(raw);bank={};rejected=[]
    for row in records:
        accepted=[]
        for candidate in row['alternatives']:
            text=candidate['text'];flags=validate(row['source'],text)
            if text.casefold().strip(' .')==row['source'].casefold().strip(' .'):flags.append('unchanged')
            if flags:rejected.append({'source':row['source'],'text':text,'flags':flags})
            elif text not in accepted:accepted.append(text)
        bank[row['source']]=accepted
    write_json(folder/'bank.json',bank);write_jsonl(folder/'post-validation-rejections.jsonl',rejected)
    write_json(folder/'sealed.json',{'manifest':manifest({'identical_alternatives_rejected':True},[raw,folder/'bank.json']),'source_phrases':len(bank),'with_changed_alternative':sum(bool(v) for v in bank.values()),'rejected_alternatives':len(rejected),'semantic_equivalence_not_proven_by_structural_checks':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);a=p.parse_args();main(a.limit)
