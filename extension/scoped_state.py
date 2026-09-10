"""Ablate requirement-scope replacement separately from semantic retrieval."""
from collections import Counter
import re
from extension.rag import RAGAgent

MARKER=r'\b(?:initial|earlier|previous) (?:feature )?(?:requirement|preference)\b[^:]*:'
REPLACE=re.compile(r'\b(?:replace|discard|drop|ignore) (?:my |the )?(?:initial|earlier|previous) (?:feature )?(?:requirement|preference)\b',re.I)


class ScopedRAGAgent(RAGAgent):
    @staticmethod
    def _incoming(text,turn):
        constraints=RAGAgent._incoming(text,turn);used=Counter()
        for c in constraints:
            if c['attribute']=='budget':continue
            identity=(c['attribute'],c['value']);matches=list(re.finditer(r'\b'+re.escape(str(c['value']))+r'\b',text,re.I));index=used[identity];used[identity]+=1
            if index<len(matches) and re.search(MARKER,text[:matches[index].start()],re.I):c['scope']='stated_requirement'
        return constraints
    def _state(self,state,text,turn):
        if REPLACE.search(text):
            state['messages']=[re.split(MARKER,message,maxsplit=1,flags=re.I)[0] for message in state['messages']]
            for constraint in state['constraints']:
                if constraint.get('scope')=='stated_requirement':constraint['replaced']=True
            # Explicit replacement is a correction event, including when the user
            # does not preface it with "actually".
            if not re.search(r'\bactually\b',text,re.I):text='Actually, '+text
        return super()._state(state,text,turn)
