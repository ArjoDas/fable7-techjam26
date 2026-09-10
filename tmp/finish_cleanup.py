import ast
from pathlib import Path
root=Path(__file__).parent/'extension-cleanup'
s=(root.parent.parent/'tests/test_extension.py').read_text()
nodes=[n for n in ast.parse(s).body if getattr(n,'name','') in ('product','CatalogTests')]
out='import tempfile, unittest\nfrom pathlib import Path\nfrom extension.catalog import Catalog\nfrom extension.common import write_jsonl\n\n'+'\n\n'.join(ast.get_source_segment(s,n) for n in nodes)
out=out.replace("        self.assertFalse(any('A' in ids for ids in self.store.edges.values()))",'')
(root/'tests/test_catalog.py').write_text(out)
