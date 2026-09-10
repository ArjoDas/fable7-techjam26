# Query language × catalog growth

This campaign isolates language changes from catalog construction. It preserves
the original agent and unmodified official evaluator. Earlier extension results
remain under their original artifact names; they are not evidence for this matrix.

## Reproduce

From the repository root, using the existing local model runtime on port 8091:

```powershell
venv/Scripts/python.exe -m unittest discover -s tests -q
venv/Scripts/python.exe -m extension.matrix.prepare
venv/Scripts/python.exe -m extension.matrix.validate
venv/Scripts/python.exe -u -m extension.matrix.bank
venv/Scripts/python.exe -u -m extension.matrix.campaign
```

The campaign can coexist with an already-running bank generator, but waits for
generation to finish before Qwen serving measurements. Do not run two campaign
controllers concurrently. It has resumable result checkpoints and stops on failed
index parity or failed commands. Check `data/releases/extension-v1/matrix/current.json`
and the corresponding file in `matrix/logs/`. Run `extension.matrix.report` to
refresh `docs/query-data-matrix.md` and its figures. A running or completed command
does not establish that a release gate passed.

Individual development screens:

```powershell
venv/Scripts/python.exe -m extension.matrix.growth --schedule frozen --size 50000
venv/Scripts/python.exe -m extension.matrix.regression
venv/Scripts/python.exe -m extension.matrix.evaluate --schedule frozen --size 50000 --variant main --level constrained --limit 120 --label manual
venv/Scripts/python.exe -m extension.matrix.evaluate --schedule frozen --size 50000 --variant rules --level wording --limit 120 --label manual
venv/Scripts/python.exe -m extension.matrix.evaluate --schedule frozen --size 50000 --variant qwen --level semantic --limit 120 --label manual
```

Result filenames are immutable within a label. Use another label for an intentional
repeat; do not overwrite negative findings. `screen` records the initial parser;
`screen-v2` preserves evidence punctuation and units. Full development and sealed
phases are separate. Raw source records, datasets, event streams, generated
alternatives, rejected output and traces remain local under `matrix/`.

## Controlled behavior

- Catalog schedules: 40k→41k→45k→50k; sensitivity 30k→40k→50k;
  Amazon expansion 50k→51k→55k→60k. Frozen 50k is a separate control.
- Starting subsets and addition order are stratified by category/popularity.
  The reused task allocation has 1,600 train, 800 development and 800 test targets.
  Four evaluator scenarios receive an approximately uniform, seeded assignment;
  their actual counts are reported, rather than assumed to match public proportions.
- The experimental loop delegates disclosure and scenario behavior to official
  evaluator functions. Only rendering changes. Fixed replay uses `other` requests.
- Wording variants retain literal evidence. Semantic variants use frozen local
  paraphrases; failed structural validation falls back to literal values and is
  counted explicitly. AI review of 200 development examples is not human validation.
- Translation uses active-catalog evidence only, never target IDs, hidden intent
  cards, original turn text or paraphrase lookup keys. Catalog-wide evidence
  preprocessing preserves literal source punctuation alongside main's normalized
  index. The model may select supplied evidence references; uncertain conversion
  falls back to main on raw input. Valid protocol turns bypass all models.
- Main's learned weights stay frozen. Batch residual adjustment is a separate
  training-only experiment with replay, not part of the primary matrix.
- Incremental snapshots preserve original product ordinals. Readers use the
  actual published indexes, not newly rebuilt substitutes. Independent rebuilds
  verify candidate pools, ranked recommendations and complete conversations.
- Clean-cache embedding experiments disable the existing 60k cache. They encode
  only current/arriving product passages. Interrupted attempts are retained and
  a fresh attempt starts with an empty cache. Accuracy screens may reuse retained
  vectors for active products; their cache hits are not claimed as ingestion work.

## Interpretation

Only the public unchanged-50k result is official compatibility. Other TechnicalScore
values use the same formula but are experimental. Report five-turn recovery and
candidate recall separately from the full ten-turn evaluator metrics. Compare
old/new products and persistent/newly-introduced cohorts separately. Three language
seeds are clustered by product for paired bootstrap intervals.

Targets remain HR@10 ≥90% and Recall@100 ≥95% by turn five, separately for old/new
products, positive paired sealed improvement, and p99 ≤2 seconds at five response
requests/second with ≤1% failures. Selected load configuration receives three
10,000-request runs and a 30-minute soak. Smaller offline screens do not qualify
production p99. Graph/LightRAG and further paid API experiments are deferred.
