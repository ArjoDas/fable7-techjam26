import ast
from pathlib import Path
root=Path(__file__).parent/'extension-cleanup'
root=root.resolve()
assert root.name=='extension-cleanup' and (root/'.git').is_file()
def read(p):return (root/p).read_text(encoding='utf-8')
def write(p,s):(root/p).write_text(s,encoding='utf-8')
def select(s,names):
    return '\n\n'.join(ast.get_source_segment(s,n) for n in ast.parse(s).body if getattr(n,'name',None) in names)+'\n'
events=read('extension/matrix/events.py')
write('extension/events.py','"""Structured customer turns and canonical protocol rendering."""\nfrom dataclasses import dataclass\nimport re\n\n'+select(events,{'Event','decode','canonical'}).replace('class Event:', '@dataclass(frozen=True)\nclass Event:'))
write('extension/translate.py',read('extension/matrix/translate.py').replace('extension.matrix.events','extension.events').replace('from extension.agent import Agent','from extension.protocol import ProtocolGuard').replace('self.guard=Agent(catalog=store)','self.guard=ProtocolGuard(catalog=store)'))
agent=read('extension/agent.py')
guard=agent[:agent.index('    @staticmethod\n    def _incoming')]
guard=guard.replace('from extension.lexical import Lexical\n','').replace('class Agent:','class ProtocolGuard:')
write('extension/protocol.py',guard)
ingest=read('extension/ingest.py')
write('extension/ingest.py','"""Normalize retained Amazon metadata for provenance-checked registration."""\n\n'+select(ingest,{'normalize'}))
catalog=read('extension/catalog.py')
start=catalog.index('    def _rebuild_graph(');end=catalog.index('    def checkpoint(',start)
catalog=catalog[:start]+catalog[end:]
catalog=catalog.replace('        self._rebuild_graph()\n','').replace('            self._replace_edges(a,p)\n','')
start=catalog.index('        if self.technique==\'rebuild\':',catalog.index('    def _refresh'))
end=catalog.index('        for a,p in changed.items():',start)
catalog=catalog[:start]+"        replacement=self._build({a:p for a,p in changed.items() if p is not None})\n        try:self._splice(replacement,changed)\n        finally:replacement.connection.close()\n"+catalog[end:]
catalog=catalog.replace(", technique='incremental'",'').replace(';self.technique=technique','').replace("        if self.technique=='rebuild':self.rowids=dict(self.agent.connection.execute('SELECT parent_asin,rowid FROM products'))\n",'').replace("len(self.products) if self.technique=='rebuild' else len(changed)",'len(changed)')
write('extension/catalog.py',catalog)
passages=read('extension/passages.py').split('\ndef prepare(')[0]
passages=passages.replace('import argparse\n','').replace('ARTIFACTS,read_jsonl,write_json,manifest','ARTIFACTS').replace('use_base_cache=True','use_base_cache=False')
write('extension/passages.py',passages)
service=read('extension/service.py').replace('    from extension.agent import Agent\n','').replace('    from extension.vectors import VectorIndex\n','')
line=next(l for l in service.splitlines() if "parser.add_argument('--variant'" in l)
service=service.replace(line,"    parser.add_argument('--variant', choices=['rules','qwen'], default='rules')")
write('extension/service.py',service)
write('extension/factory.py','''"""Construct the supported conversation routes."""
from extension.translate import TranslatedAgent

def create(store, variant='rules', worker_id=None):
    if variant not in ('rules', 'qwen'):
        raise ValueError('Supported routes are rules and qwen')
    vectors = None
    if variant == 'qwen':
        from extension.passages import PassageIndex
        vectors = PassageIndex(store, namespace='default' if worker_id is None else str(worker_id))
    return TranslatedAgent(store, mode=variant, vectors=vectors)
''')
common=read('extension/common.py')
write('extension/common.py',common[:common.index('\ndef manifest(')])
# Keep targeted update/parser/worker tests, remove campaign-dependent test cases.
source=read('tests/test_matrix.py');tree=ast.parse(source);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
methods=[ast.get_source_segment(source,n) for n in cls.body if isinstance(n,ast.FunctionDef) and ('test_converter_' in n.name or 'test_matrix_worker' in n.name)]
write('tests/test_extension_runtime.py',"import tempfile, unittest\nfrom pathlib import Path\nfrom extension.common import write_jsonl\nfrom extension.translate import Converter\n\n"+select(source,{'product'})+'\nclass RuntimeTests(unittest.TestCase):\n'+ '\n'.join('    '+m.replace('\n','\n    ') for m in methods).replace("variant='matrix-rules'","variant='rules'")+'\n')
semantic=read('tests/test_semantic_extension.py');tree=ast.parse(semantic)
prefix=semantic[:semantic.index('class Semantic')].replace('from extension.rag import RAGAgent\n','')
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and any(isinstance(m,ast.FunctionDef) and m.name.startswith('test_') for m in n.body))
methods=[ast.get_source_segment(semantic,n) for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('test_passage_deletion_reintroduction_uses_retained_vectors','test_metadata_update_encodes_only_changed_passages')]
write('tests/test_incremental_vectors.py',prefix+'class VectorTests(unittest.TestCase):\n'+'\n'.join('    '+m.replace('\n','\n    ') for m in methods)+'\n')
keep={'__init__.py','catalog.py','index.py','common.py','ingest.py','models.py','passages.py','protocol.py','events.py','translate.py','factory.py','service.py','README.md'}
# Delete only enumerated files inside the isolated worktree; previous commits retain history.
for folder in ('extension','scripts','experiments'):
    base=root/folder
    for p in list(base.rglob('*')) if base.exists() else []:
        if p.is_file() and '__pycache__' not in p.parts and (folder!='extension' or p.parent!=base or p.name not in keep):
            assert p.resolve().is_relative_to(root)
            p.unlink()
for rel in ('tests/test_extension.py','tests/test_matrix.py','tests/test_semantic_extension.py','tests/paraphrase_harness.py','EXPERIMENTS.md','README_DEV.md','docs/extension-results.md','docs/query-data-matrix.md'):
    (root/rel).unlink(missing_ok=True)
for rel in ('docs/extension-figures','docs/matrix-figures'):
    for p in (root/rel).glob('*'):
        if p.is_file():p.unlink()
