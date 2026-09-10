from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'data/releases/extension-v1'
MODEL_CACHE = ROOT / 'data/releases/real-world-v1/models'


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def manifest(config, inputs=()):
    try:
        import psutil
        resources = {'physical_cpus': psutil.cpu_count(logical=False), 'ram_gib': psutil.virtual_memory().total / 2**30, 'available_ram_gib': psutil.virtual_memory().available / 2**30, 'cpu_percent_snapshot': psutil.cpu_percent()}
    except ImportError:
        resources = {}
    model_path=MODEL_CACHE/'manifest.json'
    model_info=json.loads(model_path.read_text(encoding='utf-8')) if model_path.exists() else {}
    provenance_files=[ARTIFACTS/p for p in ('models/manifest.json','models/fp32_source.json','models/embeddings_manifest.json','router.joblib','sources/catalog_manifest.json')]
    return {
        'seed_default':20260910,
        'model_revisions':{k:model_info[k] for k in ('qwen_revision','minilm_revision','llama_tag') if k in model_info},
        'artifact_provenance_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in provenance_files if p.exists()},
        'resources': resources,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_hashes': {str(p.relative_to(ROOT)): sha256(p) for folder in ('extension', 'starter', 'evaluator') for p in sorted((ROOT / folder).glob('*.py'))},
        'python': platform.python_version(), 'platform': platform.platform(),
        'logical_cpus': os.cpu_count(), 'config': config,
        'inputs': {str(p): sha256(p) for p in inputs},
    }


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def latency_summary(values):
    return {'count': len(values), **{f'p{q}_ms': percentile(values, q / 100) for q in (50, 95, 99)}, 'tail_under_sampled': len(values) < 10000}
