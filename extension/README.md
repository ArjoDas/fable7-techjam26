# Extension campaign

This branch starts at main `c9d7da86a41c112c5c59b44277db4189ed12fd9c`.
The previous campaign is preserved on `codex/real-world-evaluation` at `b13df08`.
The official agent and evaluator remain unchanged. This package adds the catalog,
route wrapper, and separately labeled experiments.

Run commands from the repository root with `venv/Scripts/python.exe`.
Large source records, generated dialogues, snapshots, event logs, measurements,
and API-call records are retained under `data/releases/extension-v1/` and ignored
by Git. Model weights reuse the pinned cache in `data/releases/real-world-v1/models/`.
Never load a catalog snapshot from an untrusted source: its local state file uses pickle.

## Reproduction

```powershell
venv/Scripts/python.exe -m unittest discover -s tests -q
venv/Scripts/python.exe -m extension.ingest
.venv-embed/Scripts/python.exe -m extension.vectors --gpu
venv/Scripts/python.exe -m extension.baseline --historical
venv/Scripts/python.exe -m extension.datasets prepare
venv/Scripts/python.exe -m extension.runtime
# In another terminal, after the local model is ready:
venv/Scripts/python.exe -m extension.datasets generate --split train
venv/Scripts/python.exe -m extension.datasets generate --split dev
venv/Scripts/python.exe -m extension.datasets generate --split test
venv/Scripts/python.exe -m extension.audit fetch
venv/Scripts/python.exe -m extension.audit diagnostics
venv/Scripts/python.exe -m extension.audit audit
venv/Scripts/python.exe -m extension.update_benchmark --label fresh-run
venv/Scripts/python.exe -m extension.batched_updates
venv/Scripts/python.exe -m extension.representation_benchmark
venv/Scripts/python.exe -m extension.learned train
venv/Scripts/python.exe -m extension.learned score
venv/Scripts/python.exe -m extension.residual --limit 200
venv/Scripts/python.exe -m extension.evaluate --variant tinybert-lexical --split dev
venv/Scripts/python.exe -m extension.api_benchmark --limit 12 --timeout 1.2
```

Generation is resumable and preserves completed rows. Existing source files are
not overwritten. Use a fresh update-run label to repeat its whole sequence.
API experiments enforce a $10 campaign cap, with $2/$6/$2 stage caps. Unknown
usage after timeouts retains its maximum reservation. Environment credentials
are read inside the provider process and never written to manifests.

Stop generation and preprocessing before serving measurements. The LightRAG
pilot uses a fresh persistent directory and an external time/RSS watchdog:

```powershell
venv/Scripts/python.exe -m extension.lightrag_benchmark --size 100 --seconds 1200
venv/Scripts/python.exe -m extension.service --workers 4 --variant tinybert-lexical
venv/Scripts/python.exe -m extension.load --workload data/releases/extension-v1/load/workload.jsonl --rate 5 --requests 10000 --users 10 --name confirmation-1
```

The localhost service exposes GET readiness and POST `/reset`, `/respond`,
`/close`, and `/catalog_update`. Responses include queue/service timings and
route traces. Catalog publication has a single durable coordinator and waits
for all workers to acknowledge the committed version. Retries are idempotent
by session/request ID; changed request bodies are rejected, and cached product
IDs are checked against current availability before being returned.

## Interpretation

Official compatibility is measured only against the unchanged 50,000 products.
The paired expanded-catalog benchmark has its own metrics. Exploratory screens
with fewer than 10,000 responses do not establish production p99 latency.
Generation and other preprocessing may run during accuracy-only screens;
final load measurements must be isolated and pass the resource continuity check.

Release gates remain HitRate@10 1.0, MRR 1.0, MTTC 2.1, TechnicalScore 0.978 on
public; natural-query Recall@100 >=95% and HitRate@10 >=90% separately for old
and new products; positive paired sealed improvement; p99 <=2 seconds and
<=1% failures at five response requests/second; incremental/rebuild parity,
restart recovery, and no unavailable-product leaks. Failed gates stay failed.

Field-vector composition and catalog centroids are separate representation
experiments. They do not modify encoder weights or claim neural knowledge
has been subtracted. Metadata withdrawal and availability changes are
experimental events, not Amazon history. Synthetic outcomes are not evidence
of conversion or customer-satisfaction gains.
