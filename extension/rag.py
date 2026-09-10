"""Query normalization before hybrid retrieval; original constraints remain authoritative."""
import time
from extension.agent import Agent


class RAGAgent(Agent):
    def __init__(self,*args,parser=None,**kwargs):
        super().__init__(*args,**kwargs);self.parser=parser;self.parser_timeout=1.2
    def _state(self,state,text,turn):
        correction,full=super()._state(state,text,turn)
        state['parser_trace']={'called':False,'fallback':None}
        if self.parser is not None and turn==getattr(self,'active_turn',turn):
            remaining=min(self.parser_timeout,max(0,getattr(self,'request_deadline',time.perf_counter()+2)-time.perf_counter()-.7))
            if remaining>.05:
                started=time.perf_counter();state['parser_trace']['called']=True;self.model_calls+=1
                try:
                    # Parse the corrected active history, not replaced preferences.
                    result,usage=self.parser.match(' '.join(state['messages']),[],remaining)
                    normalized=result['query'].strip()
                    if not normalized:raise ValueError('Empty normalized query')
                    state['retrieval_query']=normalized
                    state['parser_trace'].update(normalized_query=normalized,usage=usage)
                except Exception as exc:state['parser_trace']['fallback']=type(exc).__name__
                state['parser_trace']['elapsed_ms']=(time.perf_counter()-started)*1000
        return correction,full
    def _respond(self,sid,message,turn,top_k):
        self.active_turn=turn
        result=super()._respond(sid,message,turn,top_k)
        if self.trace[sid]['route']!='protocol':
            info=self.states[sid].get('parser_trace',{});self.trace[sid]['parser']=info
            self.trace[sid]['model_calls']=int(info.get('called',False))
            self.trace[sid]['fallback_reason']=info.get('fallback')
            self.trace[sid]['route']='rag-'+self.trace[sid]['route']
        return result
