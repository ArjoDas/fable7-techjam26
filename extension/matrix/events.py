"""Lossless decoding of evaluator turns; rendering alone changes the language."""
from dataclasses import dataclass,asdict
import re
from extension.matrix.common import stable

@dataclass(frozen=True)
class Event:
    kind:str
    category:str=''
    values:tuple=()
    attribute:str=''

def decode(text):
    if text.startswith("I'm looking for "):
        body=text[len("I'm looking for "):]
        if body.endswith(", but I'm still exploring."):return Event('browse',body[:-len(", but I'm still exploring.")])
        if '. A key requirement is: ' in body:
            category,value=body.split('. A key requirement is: ',1);return Event('opening',category,(value[:-1],))
        category,value=body.split('. ',1);return Event('opening_old',category,(value,))
    if text.startswith('For that, what matters is: '):return Event('disclosure',values=tuple(text[len('For that, what matters is: '):-1].split('; ')))
    if text.startswith('Actually, ignore my earlier preference. What I need is: '):return Event('override',values=(text[len('Actually, ignore my earlier preference. What I need is: '):-1],))
    match=re.fullmatch("I don't have a preference for (.+); please use your judgment\\.",text)
    if match:return Event('boundary',attribute=match[1])
    match=re.fullmatch("I don't have an additional preference for (.+)\\.",text)
    if match:return Event('missing',attribute=match[1])
    if text=='Those options are not quite right yet. Ask me about one specific attribute.':return Event('ask')
    raise ValueError('Unrecognized official event')

def canonical(event):
    e=event
    if e.kind=='opening':return f"I'm looking for {e.category}. A key requirement is: {e.values[0]}."
    if e.kind=='opening_old':return f"I'm looking for {e.category}. {e.values[0]}"
    if e.kind=='browse':return f"I'm looking for {e.category}, but I'm still exploring."
    if e.kind=='disclosure':return 'For that, what matters is: '+'; '.join(e.values)+'.'
    if e.kind=='override':return 'Actually, ignore my earlier preference. What I need is: '+e.values[0]+'.'
    if e.kind=='boundary':return f"I don't have a preference for {e.attribute}; please use your judgment."
    if e.kind=='missing':return f"I don't have an additional preference for {e.attribute}."
    if e.kind=='ask':return 'Those options are not quite right yet. Ask me about one specific attribute.'
    raise ValueError(e.kind)

TRAIN={
 'opening':['I need {category}. The important part is {values}.','Can you find {category}? It needs to be {values}.'],
 'opening_old':['I need {category}. My preference is {values}.','Can you find {category}? I prefer {values}.'],
 'browse':['I am browsing {category}, with no particular choice yet.','Show me some {category}; I am still deciding.'],
 'disclosure':['My preferences are {values}.','What I care about is {values}.'],
 'override':['Change of plan: drop my previous preference. I need {values}.','Actually, replace what I said earlier with {values}.'],
 'boundary':['I am flexible about {attribute}; you can decide.','Please choose the {attribute} for me.'],
 'missing':['Nothing else to add about {attribute}.','No further requirements for {attribute}.'],
 'ask':['Could you ask about a specific attribute? These are not right yet.','These do not fit yet; ask me one specific question.']}
TEST={
 'opening':['Help me shop for {category}. My requirement is {values}.','I am after {category}. What I need is {values}.'],
 'opening_old':['Help me shop for {category}. I prefer {values}.','I am after {category}. My preference is {values}.'],
 'browse':['Let me browse {category}; I have not decided yet.','I am exploring options for {category}, still undecided.'],
 'disclosure':['The requirements I have are {values}.','I would prioritize {values}.'],
 'override':['Forget that earlier preference; use {values} instead.','I changed my mind. Replace my earlier preference with {values}.'],
 'boundary':['The {attribute} is up to you.','You decide on {attribute}; I have no preference.'],
 'missing':['I have nothing more to specify about {attribute}.','There is no extra requirement for {attribute}.'],
 'ask':['Please narrow this down by asking about one attribute.','Not the right options yet; please ask one attribute question.']}

def render(event,level,sample_id,seed,split,bank=None):
    if level=='constrained':return canonical(event),[]
    payload=asdict(event);rng=int(stable((sample_id,seed,payload)),16);fallback=[]
    def phrase(value):
        if level!='semantic':return value
        choices=(bank or {}).get(value,[])
        if not choices:fallback.append(value);return value
        return choices[rng%len(choices)]
    templates=(TEST if split=='test' else TRAIN)[event.kind]
    return templates[rng%len(templates)].format(category=phrase(event.category) if event.category else '',values='; '.join(phrase(v) for v in event.values),attribute=event.attribute),fallback
