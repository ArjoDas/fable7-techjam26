"""Structural validation and disclosure audits before quality comparisons."""
from collections import Counter
from evaluator import local_evaluator as official
from extension.matrix.common import *
from extension.matrix.events import TRAIN,TEST,decode,canonical,render

def main():
    products={p['parent_asin']:p for p in read_jsonl(HOME/'prepared/ordered-products.jsonl')};seen=set();counts={};flags=[];turn_count=0
    assert len(products)==60000
    assert not {t for values in TRAIN.values() for t in values}&{t for values in TEST.values() for t in values}
    for split,n in (('train',1600),('dev',800),('test',800)):
        rows=read_jsonl(HOME/f'prepared/{split}.jsonl');ids={r['ground_truth']['parent_asin'] for r in rows}
        assert len(rows)==len(ids)==n and not ids&seen and ids<=set(products);seen.update(ids);counts[split]=dict(Counter(r['scenario_type'] for r in rows))
        for row in rows:
            target=row['ground_truth']['parent_asin'];product=products[target];disclosed=set();boundary=False;changed=row['scenario_type']!='intent_override';text=official.initial_message(row,official.coarse_category(product.get('categories',[])),disclosed)
            for turn in range(1,11):
                event=decode(text);assert canonical(event)==text
                for seed in SEEDS:
                    natural,_=render(event,'wording',row['sample_id'],seed,split)
                    assert all(v in natural for v in event.values)
                if target in text:flags.append({'sample_id':row['sample_id'],'turn':turn,'flag':'identifier_in_official_disclosure'})
                title=str(product.get('title','')).strip()
                if len(title)>15 and title.casefold() in text.casefold():flags.append({'sample_id':row['sample_id'],'turn':turn,'flag':'title_in_official_disclosure'})
                turn_count+=1;override=row.get('behavior',{}).get('override') or {}
                if not changed and turn+1==int(override.get('turn',3)):
                    changed=True;text=override['message'];disclosed.add(override['new_value'])
                else:text,boundary=official.customer_reply(row,'other',disclosed,boundary)
    write_json(HOME/'validation.json',{'manifest':manifest({},[HOME/f'prepared/{s}.jsonl' for s in counts]),'split_disjoint':True,'scenario_counts':counts,'validated_canonical_turns':turn_count,'held_out_template_families':True,'flags':flags,'note':'Title/identifier disclosures inherited from the official simulator are flagged, not introduced to force recovery.'})
    print('Validated',turn_count,'canonical turns and paired wording renderings',flush=True)

if __name__=='__main__':main()
