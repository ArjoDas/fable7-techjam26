"""Protocol-compatible happy path with typed state for unfamiliar conversations."""
from collections import Counter, defaultdict
import re
import time
from starter.agent import Agent as MainAgent, _terms, _normalized_value, MATERIAL_TERMS, COLOR_TERMS
from starter.cp5_dialogue import normalize_protocol_text
from extension.lexical import Lexical

ATTRS='category|material|color|size|style|brand|budget|feature|use_case|other'
OPEN=re.compile(r"I'm looking for (.+?)(?:, but I'm still exploring\.|\. (.+))",re.I)
REPLY=re.compile(r'For that, what matters is: (.+)\.',re.I)
OVERRIDE=re.compile(r'Actually, ignore my earlier preference\. What I need is: (.+)\.',re.I)
EMPTY=re.compile(r"I don't have (?:an additional preference for (?:"+ATTRS+r")\.|a preference for (?:"+ATTRS+r"); please use your judgment\.)",re.I)
GENERIC="Those options are not quite right yet. Ask me about one specific attribute."


def words(text):
    return [t[:-1] if len(t)>3 and t.endswith('s') and not t.endswith('ss') else t for t in _terms(text)]


class Agent:
    def __init__(self,catalog_path='data/catalog.jsonl',catalog=None,variant='rules',vectors=None,model=None,reranker=None,router=None):
        self.catalog=catalog;self.base=catalog.agent if catalog else MainAgent(catalog_path)
        self.source_categories={}
        if catalog is None:
            import json
            with open(catalog_path,encoding='utf-8') as stream:
                for line in stream:
                    if line.strip():
                        product=json.loads(line);self.source_categories[product['parent_asin']]=product.get('categories') or []
        self.variant=variant;self.vectors=vectors;self.model=model;self.reranker=reranker;self.router=router
        self.states={};self.trace={};self.model_calls=0;self._version=-1;self._prepare()

    def _prepare(self,changed=None):
        if changed is None:
            self.protocol_values=defaultdict(set);self.category_ids=defaultdict(set);self.aliases=defaultdict(set)
            self.product_tokens={};self.product_aliases={};self.product_cards={}
            changed=list(self.base._dialogue_index.cards)
        for asin in changed:
            previous=self.product_cards.pop(asin,None)
            if previous:
                self.category_ids[previous.category].discard(asin)
                for value in previous.sequence:
                    key=(previous.category,value);self.protocol_values[key].discard(asin)
                    if not self.protocol_values[key]:del self.protocol_values[key]
            for alias in self.product_aliases.pop(asin,()):
                self.aliases[alias].discard(asin)
                if not self.aliases[alias]:del self.aliases[alias]
            self.product_tokens.pop(asin,None)
        stop=MATERIAL_TERMS|COLOR_TERMS|{'men','women','clothing','accessory','shoe','jewelry','home','kitchen','electronics','boy','girl','baby'}
        for asin in changed:
            card=self.base._dialogue_index.cards.get(asin)
            if card is None:continue
            self.product_cards[asin]=card;self.product_aliases[asin]=set()
            self.category_ids[card.category].add(asin)
            for value in card.sequence:self.protocol_values[(card.category,value)].add(asin)
            view=self.base._product_views[asin];self.product_tokens[asin]=frozenset(_terms(' '.join(view[:6])))
            # Taxonomy-derived phrases only: never turn arbitrary material mentions into categories.
            p=self.catalog.products[asin] if self.catalog else None
            categories=p.get('categories',[]) if p else self.source_categories.get(asin,[view[1]])
            for category in categories[-3:]:
                phrase=' '.join(words(str(category)))
                if phrase and set(phrase.split())-stop and not re.search(r'\b(?:wash|imported|made|ready|closure)\b',phrase):
                    self.aliases[phrase].add(asin)
                    self.product_aliases[asin].add(phrase)
        self.alias_pattern=re.compile(r'\b(?:'+'|'.join(re.escape(a) for a in sorted(self.aliases,key=len,reverse=True))+r')\b') if self.aliases else None
        self._version=self.catalog.version if self.catalog else 0

    def reset(self,session_id,user_profile):
        self.base.reset(session_id,user_profile)
        self.states[session_id]={'protocol':True,'category':'','possible':None,'constraints':[], 'messages':[],
                                 'mode':'buying','turn':0,'seen':set(),'profile':user_profile,'ask':None,'category_alias':'','protocol_history':[]}

    def close(self,session_id):
        self.states.pop(session_id,None);self.trace.pop(session_id,None);self.base._sessions.pop(session_id,None)

    def _protocol(self,state,text,turn):
        if not state['protocol']:return False
        if turn==1:
            match=OPEN.fullmatch(text)
            if not match:return False
            category=_normalized_value(match[1])
            if category not in self.category_ids:return False
            state['category']=category;possible=self.category_ids[category]
            value=match[2]
            if value:
                value=re.sub(r'^A key requirement is: ','',value,flags=re.I).rstrip('.')
                for part in value.split(';'):
                    possible=possible & self.protocol_values.get((category,_normalized_value(part)),set())
            if not possible:return False
            state['possible']=possible;return True
        if turn!=state['turn']+1:return False
        state['possible']=state.get('possible',set()) & self.category_ids.get(state['category'],set())
        if not state['possible']:return False
        if EMPTY.fullmatch(text):
            return state['ask'] is not None and bool(re.search(r'for '+re.escape(state['ask'])+r'(?:;|\.)',text))
        if text==GENERIC:return state['ask'] is None
        match=OVERRIDE.fullmatch(text) or REPLY.fullmatch(text)
        if not match:return False
        possible=self.category_ids[state['category']] if OVERRIDE.fullmatch(text) else state['possible']
        for part in match[1].split(';'):possible=possible & self.protocol_values.get((state['category'],_normalized_value(part)),set())
        if not possible:return False
        state['possible']=possible;return True

    @staticmethod
    def _incoming(text,turn):
        result=[]
        for attribute,values in (('color',COLOR_TERMS),('material',MATERIAL_TERMS)):
            for match in re.finditer(r'\b(?:'+'|'.join(sorted(values))+r')\b',text,re.I):
                before=text[max(0,match.start()-30):match.start()].lower()
                negative=bool(re.search(r'(?:\bno|\bnot|without|avoid|except|instead of)\s+(?:any\s+)?$',before))
                result.append({'attribute':attribute,'value':match[0].lower(),'polarity':not negative,'turn':turn,'replaced':False})
        budget=re.search(r'(?:under|below|at most|less than|budget(?: of)?)\s*\$?\s*(\d+(?:\.\d+)?)',text,re.I)
        if budget:result.append({'attribute':'budget','value':float(budget[1]),'polarity':True,'turn':turn,'replaced':False})
        return result

    def _state(self,state,text,turn):
        learned_label,learned_confidence=self.router.predict(text,' '.join(state['messages'])) if self.router else ('',0.)
        state['router_prediction']={'label':learned_label,'confidence':learned_confidence}
        incoming=self._incoming(text,turn)
        category_text=re.sub(r"(?:I don't want|not looking for|no)\s+[^.]+\.", '',text,flags=re.I)
        matches=list(self.alias_pattern.finditer(' '.join(words(category_text)))) if self.alias_pattern else []
        alias=max((m[0] for m in matches),key=lambda x:(len(x.split()),len(x)),default='')
        correction=bool(re.search(r'\b(?:actually|instead|switch to|change to|forget|ignore my earlier)\b',text,re.I))
        full=bool(re.search(r'\b(?:different category|forget everything|completely different)\b',text,re.I))
        if learned_confidence>=.8 and learned_label in ('partial_override','category_override'):correction=True
        if learned_confidence>=.9 and learned_label=='category_override':full=True
        if correction and alias and state['category_alias']:
            full=full or not bool(self.aliases[alias] & self.aliases[state['category_alias']])
        if full:
            reset_everything=bool(re.search(r'\bforget everything\b',text,re.I))
            for c in state['constraints']:
                if reset_everything or c['attribute']!='budget':c['replaced']=True
            state['messages']=[];state['seen'].clear();state['category_alias']=''
        elif correction:
            if re.search(r'replace my initial feature requirement',text,re.I):
                state['messages']=[m.split('My initial feature requirement is:',1)[0] for m in state['messages']]
            attrs={c['attribute'] for c in incoming if c['polarity']}
            for old in state['constraints']:
                if old['attribute'] in attrs or any(c['attribute']==old['attribute'] and c['value']==old['value'] and not c['polarity'] for c in incoming):old['replaced']=True
            stale={str(c['value']) for c in state['constraints'] if c['replaced']}
            state['messages']=[re.sub(r'\b(?:'+'|'.join(map(re.escape,stale))+r')\b','',m,flags=re.I) if stale else m for m in state['messages']]
            state['seen'].clear()
        category_cue=bool(re.search(r'\b(?:need|want|looking for|switch|category|instead|forget)\b',text,re.I))
        if alias and (turn==1 or (category_cue and (correction or not state['category_alias']))):state['category_alias']=alias
        state['constraints'].extend(incoming);state['messages'].append(text)
        if re.search(r'\b(?:browsing|exploring|compare|not sure|options)\b',text,re.I):state['mode']='browsing'
        if re.search(r'\b(?:buy|purchase|order now|ready to)\b',text,re.I):state['mode']='buying'
        if learned_confidence>=.8 and learned_label in ('buying','browsing'):state['mode']=learned_label
        return correction,full

    def _allowed(self,asin,constraints):
        if self.catalog and (asin not in self.catalog.products or not self.catalog.products[asin].get('available',True)):return False
        tokens=self.product_tokens.get(asin,frozenset());price=self.base._product_views[asin][6]
        for c in constraints:
            if c['attribute']=='budget':
                if price is None or price>c['value']:return False
            elif c['polarity'] and c['value'] not in tokens:return False
            elif not c['polarity'] and c['value'] in tokens:return False
        return True

    def respond(self,session_id,user_message,turn,top_k):
        if self.catalog:
            with self.catalog.lock:
                self.catalog.sync();self.base=self.catalog.agent
                if self._version!=self.catalog.version:
                    import json
                    changed=set()
                    for payload, in self.catalog.db.execute('SELECT events FROM events WHERE version>?',(self._version,)):
                        changed.update(json.loads(payload)['changed'])
                    self._prepare(changed)
                if self.vectors is not None:self.vectors.sync(self.catalog)
                return self._respond(session_id,user_message,turn,top_k)
        return self._respond(session_id,user_message,turn,top_k)

    def _respond(self,sid,message,turn,top_k):
        started=time.perf_counter();state=self.states[sid];text=normalize_protocol_text(message)
        if turn!=state['turn']+1:raise ValueError('Turns must be sequential')
        if self._protocol(state,text,turn):
            result=self.base.respond(sid,message,turn,top_k)
            state['turn']=turn;state['ask']=result['ask_attribute']
            state['protocol_history'].append((turn,text))
            self.trace[sid]={'route':'protocol','version':self._version,'model_calls':0,'candidate_ids':self.base._sessions[sid].get('last_candidates',[])}
            return result
        if state['protocol']:
            for previous_turn,previous_text in state['protocol_history']:self._state(state,previous_text,previous_turn)
        state['protocol']=False
        correction,full=self._state(state,text,turn)
        active=[c for c in state['constraints'] if not c['replaced']]
        contradiction=any(a['attribute']==b['attribute'] and a['value']==b['value'] and a['polarity']!=b['polarity'] for a in active for b in active)
        if contradiction:
            state['turn']=turn;state['ask']='other'
            self.trace[sid]={'route':'clarification','version':self._version,'constraints':active,'candidate_ids':[],'model_calls':0,'reason':'contradiction'}
            return {'message':'Those requirements conflict. Which should I keep?','ask_attribute':'other','recommendations':[]}
        query=state.pop('retrieval_query',' '.join(state['messages']));usage={};fallback=None;route='lexical';calls=0
        base_state=self.base._sessions[sid]
        base_state.update(messages=[query],base_message='',protocol_compatible=False,exploratory=state['mode']=='browsing')
        terms=list(dict.fromkeys(_terms(query)))[:80]
        candidates=Lexical(self.base)._fused_search(terms,100,route_limit=200,popularity_weight=.0 if state['mode']=='browsing' else 1.)
        base_state['query_profile']=self.base._query_profile(base_state)
        ranked=self.base._rerank(candidates,base_state,terms,len(candidates))
        lexical_confidence=max((len(set(terms)&self.product_tokens[a])/max(1,len(set(terms))) for a in ranked[:5]),default=0)
        if self.vectors is not None and (self.variant!='gated-tinybert' or lexical_confidence<.6):
            semantic=self.vectors.search(query,100,self.catalog)
            score=defaultdict(float)
            for weight,lane in ((2.0 if self.variant in ('gated-tinybert','weighted-rag') else 1.0,ranked),(1.0,semantic)):
                for i,a in enumerate(lane):score[a]+=weight/(61+i)
            ranked=sorted(score,key=lambda a:(-score[a],a));route='hybrid'
        if self.variant=='graph' and self.catalog:
            overlap=Counter()
            for edge,ids in self.catalog.edges.items():
                if set(words(edge[1])) & set(words(query)):
                    for a in ids:overlap[a]+=1/max(1,len(ids))**.5
            graph=sorted(overlap,key=lambda a:(-overlap[a],a))[:100]
            ranked=list(dict.fromkeys(ranked[:50]+graph+ranked[50:]));route='graph'
        confidence=max((len(set(terms)&self.product_tokens[a])/max(1,len(set(terms))) for a in ranked[:5]),default=0)
        if self.model is not None and (confidence<.5 or not state['category_alias']):
            timeout=min(1.2,max(0,1.8-(time.perf_counter()-started)))
            deadline=getattr(self,'request_deadline',None)
            if deadline is not None:timeout=min(timeout,max(0,deadline-time.perf_counter()-.2))
            if timeout>.05:
                try:
                    calls=1;self.model_calls+=1
                    cards=[{'ref':str(i),'category':self.base._product_views[a][1],'evidence':' '.join(self.base._product_views[a][:6])[:450]} for i,a in enumerate(ranked[:20])]
                    response,usage=self.model.match(query,cards,timeout)
                    if self.model.mode=='extraction' and isinstance(response.get('query'),str):
                        normalized=response['query'][:1500];expanded=list(dict.fromkeys(_terms(normalized)))[:80]
                        alternate=Lexical(self.base)._fused_search(expanded,100,route_limit=200)
                        alternate=self.base._rerank(alternate,base_state,expanded,len(alternate))
                        ranked=list(dict.fromkeys(alternate+ranked));route+='-extraction'
                    refs=response.get('ranking',[])
                    selected=[ranked[int(i)] for i in refs if str(i).isdigit() and 0<=int(i)<min(20,len(ranked))]
                    ranked=list(dict.fromkeys(selected+ranked));route+='-model'
                except Exception as exc:fallback=type(exc).__name__
        pool=ranked[:100]
        filtered=[a for a in pool if self._allowed(a,active)]
        alias=state['category_alias']
        if alias:
            compatible=[a for a in filtered if a in self.aliases[alias]]
            if compatible:filtered=compatible
        if self.reranker is not None and filtered:
            limit=getattr(self.reranker,'limit',20)
            filtered=self.reranker.rank(query,filtered[:limit],self.base)+filtered[limit:]
        if confidence<.08 and not alias:filtered=[]
        selected=filtered[:top_k]
        question='category' if not alias else self._question(filtered[:20],active)
        state['turn']=turn;state['ask']=question;state['seen'].update(selected)
        self.trace[sid]={'route':route,'version':self._version,'constraints':active,'override':correction,'full_override':full,
                         'category_alias':alias,'mode':state['mode'],'router':state.get('router_prediction'),'confidence':confidence,'candidate_ids':pool,
                         'model_calls':calls,'fallback_reason':fallback,'elapsed_ms':(time.perf_counter()-started)*1000}
        return {'message':'Here are matching options. What matters most next?' if selected else 'I need more detail to find a supported match. What kind of product do you need?',
                'ask_attribute':question,'recommendations':[{'parent_asin':a} for a in selected],'usage':usage}

    def _question(self,candidates,constraints):
        if self.variant=='lexical' or not candidates:return 'other'
        constrained={c['attribute'] for c in constraints}
        for attr,values in [('material',MATERIAL_TERMS),('color',COLOR_TERMS)]:
            if attr not in constrained and len({tuple(sorted(self.product_tokens[a]&values)) for a in candidates})>1:return attr
        return 'other'
