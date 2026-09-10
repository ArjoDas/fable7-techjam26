"""One route factory shared by offline evaluation and HTTP serving."""
from extension.common import ARTIFACTS


def create(store,variant,worker_id=None):
    from extension.agent import Agent
    if variant.startswith('matrix-'):
        if variant=='matrix-semantic':return create(store,'rag-passages-corrected',worker_id)
        import json
        from extension.matrix.translate import TranslatedAgent
        from extension.matrix.common import HOME
        selection=HOME/'selection.json';threshold=json.loads(selection.read_text(encoding='utf-8'))['threshold'] if selection.exists() else .65
        vectors=None
        if variant=='matrix-qwen':
            from extension.passages import PassageIndex
            vectors=PassageIndex(store,namespace='matrix' if worker_id is None else 'matrix-worker-'+str(worker_id))
        return TranslatedAgent(store,variant.removeprefix('matrix-'),vectors,threshold)
    if variant=='main':return store.agent
    semantic={'hybrid','tinybert','tinybert-100','minilm-cross','local','learned','residual','centroid','gated-tinybert','rag','rag-local'}
    vectors=model=reranker=router=None
    if variant in semantic or variant.startswith('api-'):
        from extension.vectors import VectorIndex
        vectors=VectorIndex(ARTIFACTS/'vectors/document',state_name='document' if worker_id is None else 'document-worker-'+str(worker_id));vectors.sync(store)
    if variant=='local' or variant.startswith('api-'):
        from extension.providers import Matcher
        provider='local' if variant=='local' else variant[4:].removesuffix('-extraction')
        model=Matcher(provider,mode='extraction' if variant.endswith('-extraction') else 'ranking')
    if variant in ('tinybert','tinybert-100','tinybert-lexical','gated-tinybert','minilm-cross'):
        from extension.rerankers import CrossEncoder
        reranker=CrossEncoder('minilm' if variant=='minilm-cross' else 'tinybert',limit=100 if variant in ('tinybert-100','tinybert-lexical','gated-tinybert') else 20)
    if variant=='learned':
        from extension.learned import Router
        router=Router()
    if variant=='residual':
        from extension.residual import Residual
        reranker=Residual()
    if variant in ('rag','rag-local','rag-passages','rag-passages-local','corrected-lexical','rag-passages-corrected','rag-passages-local-corrected'):
        from extension.rag import RAGAgent,CompactParser
        from extension.rerankers import CrossEncoder
        from extension.providers import Matcher
        if variant.startswith('rag-passages'):
            from extension.passages import PassageIndex
            vectors=PassageIndex(store,namespace='default' if worker_id is None else 'worker-'+str(worker_id))
        agent_class=RAGAgent
        if variant.endswith('-corrected') or variant=='corrected-lexical':
            from extension.scoped_state import ScopedRAGAgent
            agent_class=ScopedRAGAgent
        return agent_class(catalog=store,variant='weighted-rag',vectors=vectors,reranker=CrossEncoder('tinybert',limit=100),parser=CompactParser() if '-local' in variant else None)
    return Agent(catalog=store,variant=variant,vectors=vectors,model=model,reranker=reranker,router=router)
