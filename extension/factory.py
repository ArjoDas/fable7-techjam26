"""One route factory shared by offline evaluation and HTTP serving."""
from extension.common import ARTIFACTS


def create(store,variant):
    from extension.agent import Agent
    if variant=='main':return store.agent
    semantic={'hybrid','tinybert','tinybert-100','minilm-cross','local','learned','residual','centroid','gated-tinybert'}
    vectors=model=reranker=router=None
    if variant in semantic or variant.startswith('api-'):
        from extension.vectors import VectorIndex
        vectors=VectorIndex(ARTIFACTS/'vectors/document');vectors.sync(store)
    if variant=='local' or variant.startswith('api-'):
        from extension.providers import Matcher
        model=Matcher('local' if variant=='local' else variant[4:])
    if variant in ('tinybert','tinybert-100','tinybert-lexical','gated-tinybert','minilm-cross'):
        from extension.rerankers import CrossEncoder
        reranker=CrossEncoder('minilm' if variant=='minilm-cross' else 'tinybert',limit=100 if variant in ('tinybert-100','tinybert-lexical','gated-tinybert') else 20)
    if variant=='learned':
        from extension.learned import Router
        router=Router()
    if variant=='residual':
        from extension.residual import Residual
        reranker=Residual()
    return Agent(catalog=store,variant=variant,vectors=vectors,model=model,reranker=reranker,router=router)
