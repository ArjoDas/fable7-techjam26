"""Deterministic lexical ties for the extended route; main's route is untouched."""
from starter.agent import Agent


class Lexical:
    def __init__(self,base):self.base=base
    def __getattr__(self,name):return getattr(self.base,name)
    def _ranked_asins(self,expression,limit=150,category=None):
        if not expression:return []
        sql=('SELECT parent_asin FROM products WHERE products MATCH ? '+('AND coarse_category = ? ' if category else '')+
             'ORDER BY bm25(products,0.0,0.0,6.0,4.0,2.5,2.5,1.5,1.0),parent_asin LIMIT ?')
        args=(expression,category,limit) if category else (expression,limit)
        return [r[0] for r in self.base.connection.execute(sql,args)]
    _fused_search=Agent._fused_search
