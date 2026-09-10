import hashlib
from extension.common import ARTIFACTS,ROOT,manifest as base_manifest,sha256,write_json,read_jsonl,write_jsonl

HOME=ARTIFACTS/'matrix'
SEEDS=(20260910,20260911,20260912)
SCHEDULES={'within40':(40000,41000,45000,50000),'within30':(30000,40000,50000),'expanded':(50000,51000,55000,60000),'frozen':(50000,)}

def manifest(config,inputs=()):
    value=base_manifest(config,inputs)
    value['source_hashes'].update({str(p.relative_to(ROOT)):sha256(p) for p in sorted((ROOT/'extension/matrix').glob('*.py'))})
    return value

def stable(value):return hashlib.sha256(str(value).encode()).hexdigest()
