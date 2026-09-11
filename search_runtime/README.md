# Runtime configuration

Supported routes: `rules` and `minilm`. Both use main's frozen lexical retrieval and linear ranking model. `create(store)` and the CLI default to `minilm`. Diagnostics are available in `agent.trace[session_id]`.

## Optional local models

Install `requirements-semantic.txt`. Set `SEARCH_MODEL_DIR` to a directory containing `minilm/tokenizer.json` and `minilm/onnx/model_quint8_avx2.onnx` for all-MiniLM-L6-v2. Supply revision-pinned model files locally; the runtime does not download models. This CPU encoder file is approximately 23 MB; process memory is larger.

Start with `python -m search_runtime.service --source data/catalog.jsonl --catalog data/search/store --variant minilm`. No external model credentials or generative services are used. Validated protocol turns do not initialize or call MiniLM. Literal evidence and action rules run first; MiniLM compares individual phrases against up to 256 active evidence values. Acceptance requires cosine >=0.65, a >=0.05 first/second margin, and matching numbers. These conservative defaults are not a calibrated general equivalence guarantee.

Phrase vectors are encoded lazily and persisted inside the catalog store. Catalog changes update evidence reference counts only for affected products. Deleted evidence is excluded; identical reintroduced evidence reuses its cached vector. Encoder and reranker weights stay fixed. The separate `PassageIndex` utility also supports incremental product embeddings but is not loaded by this serving route. `SEARCH_DATA_DIR` overrides `data/search`.

Rules maintain a buying/browsing mode plus constraints with attribute, value, polarity, source turn, and replacement history. A partial correction replaces the affected attribute; a category change clears previous category-specific preferences. Recognized negations exclude matches. Faithfully rendered natural turns delegate through main after full protocol/evidence validation. Richer state changes use general lexical retrieval and linear reranking; undisclosed evidence is never added to synthesize a dialogue prefix. Recommendations are checked against category, known constraints, and availability. Ambiguous mapping rolls back the turn's tentative state and asks for clarification alongside lexical fallback results.

Supported examples: `I'm just browsing shirts`, `I'm ready to buy now`, `Keep cotton, make it blue instead`, `Forget shirts. I want shoes instead`, and `I need shirts, not red`. Action recognition remains rule-based: MiniLM maps evidence, not arbitrary discourse. Complex negation, comparison, numeric ranges, untyped attribute corrections, and subtle intent shifts need broader evaluation. The 1.2-second conversion budget is checked between encoding batches; it cannot interrupt an in-flight ONNX call. Cold-start or large-shortlist latency is not production-qualified.

## Source-backed additions

Register records containing `raw`, `product`, `source_category`, `source_url`, `source_line`, and `source_record_sha256`. Build `product` with `search_runtime.ingest.normalize(raw, source_category)`. URLs must be under the McAuley Amazon Reviews 2023 dataset root. Retain the original downloaded record. Registration checks normalization and records provenance; it does not independently download or authenticate the URL.

```python
store.register([record])
store.apply([{
    'parent_asin': record['product']['parent_asin'],
    'revision': 1,
    'operation': 'upsert',
    'product': record['product'],
}])
```

Deletion uses `operation='delete'`. Availability changes require an existing product and boolean `available`. Changed facts must be registered before publication. The return value is the published version. Readers refresh before serving; HTTP publication waits for worker acknowledgement. Use one publication coordinator per store.

## Verification

`python -m unittest discover tests` covers recovery, idempotency, source validation, converter refresh, worker acknowledgement, cached retry filtering, and incremental encoding. `python -m search_runtime.check_public --catalog data/catalog.jsonl` checks official metrics through the wrapper and forbids model calls.
