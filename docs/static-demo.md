# Static demo recordings

The `arjo-static-demo` frontend plays responses captured from the real local
`AgentRuntime`, including its pipeline traces and complete recommendation cards.
It never runs search, translation, or inference in the browser. Both query modes
use fixed recorded inputs. Later turns and product previews use the downloaded
session data without additional requests.

`web/public/recordings/manifest.json` lists 12 examples and their two recordings.
The 24 sessions contain 68 turns and occupy about 1.5 MB of uncompressed JSON
in total. The browser initially downloads only the index, then the selected
session when the visitor clicks **Play example**. Successful downloads are cached
in memory for replay. Failed downloads can be retried.

The manifest stores capture time, source repository and commit, a digest of the
runtime source files, catalog digest and size, and model revision/file digests.
Each response was validated against the API response schema during capture.
Capture also verifies that every final target is ranked first and that rotation
examples actually rotate. A recording timestamp and execution timings are
expected to change on regeneration; byte-for-byte replay of a fresh capture is
not promised.

## What natural-language playback demonstrates

The existing natural-language translator checks literal catalog matches before
using MiniLM. All current scripted examples resolve through those literal rules;
none required MiniLM inference or a fallback. Their saved translation diagnostics
are displayed honestly as such. MiniLM was available and warmed during capture,
but its availability must not be interpreted as usage on these turns. The live
application on [main](https://github.com/ArjoDas/fable7-techjam26/blob/main/README.md#fable7-web-demo-quickstart)
lets visitors try their own messages through the full runtime.

## Regenerate deliberately

This is a development operation, **not part of the frontend build**. It needs the
50,000-item `data/catalog.jsonl`, Python 3.10+ with SQLite FTS5, and dependencies
from `requirements-api.txt` and `requirements-semantic.txt`. Follow the catalog
setup in the repository README first.

The current recordings used `sentence-transformers/all-MiniLM-L6-v2` at revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Download the following official model
files from that revision into a local model directory:

- `minilm/tokenizer.json` from the repository's `tokenizer.json`
- `minilm/onnx/model_quint8_avx2.onnx` from `onnx/model_quint8_avx2.onnx`

The pinned model files are available in the
[model repository](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41).
The recorder does not download files. Supply the actual revision matching your
files; it records both that declaration and the file hashes for verification.

From the repository root:

```bash
python3 -m venv .venv-demo
source .venv-demo/bin/activate
python -m pip install -r requirements-api.txt -r requirements-semantic.txt
SEARCH_MODEL_DIR=/absolute/path/to/models python -m scripts.record_demo \
  --model-revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41
python -m unittest tests.test_recordings -v
```

Use `--catalog` or `--output` to override their default paths. Review the generated
JSON and provenance before committing. If the example collection changes, remove
obsolete recording files as part of that review. Do not add catalogs, model
weights, or local caches to the static website.

## Verify the exported website

Build and serve `web/out` using the root README instructions. The browser tests
cover all recorded turns in both modes, target results, replay, mode selection,
mobile widths, failed-download recovery, full product previews, keyboard focus,
and shareable URLs. `tests/e2e.mjs` blocks requests to other origins and asserts
there are no backend endpoint calls or POST requests. Google Fonts are optional;
the site uses system fallbacks if those stylesheet requests fail.

Only the files in `web/out/` need deployment. No environment variables, catalog
indexing, API readiness checks, model loading, or persistent server is involved.
