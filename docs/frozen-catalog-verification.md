# Frozen-catalog verification and frontend integration

September 11, 2026. All runs use the original **50,000 unique catalog products** and **200 public product tasks**. The official evaluator/simulator is unchanged. Natural evaluation changes only each displayed customer turn, using retained templates and the existing semantic phrase bank, seed **20260910**. The serving agent sees only the rendered turn. These are historical public-task regressions, not sealed or independent held-out quality estimates. No new generation or API calls were used.

## Final results

| Language / entry point | HitRate@10 | MRR | MTTC | Score | Recovery by turn 5 | Candidate Recall@100 by turn 5 |
|---|---:|---:|---:|---:|---:|---:|
| Original protocol, wrapper | 100% | 1.000000 | 2.10 | 0.978000 | 99% | 99.5% |
| Original protocol, actual FastAPI endpoints | 100% | 1.000000 | 2.10 | 0.978000 | — | — |
| Wording-only paraphrases | 99.5% (199/200) | 0.966139 | 2.11 | 0.965142 | 98.5% | 99.5% |
| Semantic paraphrases | 58.5% (117/200) | 0.427524 | 5.65 | 0.527757 | 58.5% | 84% |

Only the original protocol rows are **official compatibility** results. The natural rows use the same score formula but are **experimental**. MTTC includes failures as eleven turns, following the evaluator. Candidate recall is measured from the actual first 100 candidates before final ranking/filtering, cumulatively through five turns and only after an override becomes eligible.

Both official checks used zero model calls. No unhandled request errors were recorded in the natural runs. The semantic run contained 1,047 turns: 18 validated translated-protocol turns, 730 stateful general-retrieval turns, and 299 lexical/clarification fallbacks. 184 turns retained at least one literal value because the historical semantic bank lacked an alternative. Therefore this is a mixed-coverage semantic benchmark, not a guarantee that every field in every turn was paraphrased. Local encoder batch counts are in the JSON; they are not external API requests.

## Scenario recovery

| Scenario | Tasks | Wording-only | Semantic |
|---|---:|---:|---:|
| Buying | 80 | 100% | 61.25% |
| Browsing | 80 | 100% | 63.75% |
| Intent override | 30 | 100% | 36.67% |
| Boundary | 10 | 90% | 60% |

**Retain** the official route and wording-only conversion for these measured regressions. **Reject the claim that general semantic conversation handling is production-qualified.** Its 58.5% five-turn recovery and 84% candidate recall fail the unchanged 90% and 95% gates. The implementation remains available as an experimental local route, as requested; the failed gates were not relaxed.

The remaining wording failure, `public_0041`, exposes a false category change: a feature containing `women tops` was interpreted as changing the original `tees & blouses tunics` category. Semantic failures additionally show uncertain categories/evidence, bounded shortlist limitations, and weak override interpretation. Higher recall needs better parsing and candidate generation, not merely a wider final recommendation list. The earlier small MiniLM mapping smoke test did not establish full conversational retrieval accuracy.

## Corrections made during verification

The initial stateful implementation scored only 49% on wording and 6.5% on semantic paraphrases. Verification exposed implicit-availability filtering, literal-feature splitting, category-only request clauses being treated as attributes, overlapping category phrases, missing-preference handling, and loss of validated protocol delegation. These were corrected with focused tests. An intermediate version reached 86.5% wording and 59% semantic; the final version reaches 99.5% wording and 58.5% semantic. The small semantic regression is retained, not hidden. All these public-task runs are development/regression evidence after fixes.

## Integration and checks

- `sri-frontend` now initializes the shared `Catalog` plus MiniLM wrapper. Reset/close/respond go through it for both UI modes. The frontend's older independent mapper was replaced with a trace-display adapter.
- Actual FastAPI endpoints were evaluated on all 200 public tasks with tracing enabled. Every observed route was `protocol`; metrics remained 0.978 with zero model calls.
- 81 backend/unit/integration tests pass on `sri-frontend` (including preserved historical tests); 45 core tests pass on `extension-updated`. Frontend `npm run typecheck` passes.
- Existing frontend page and CSS changes were preserved. The tested runtime is isolated under `search_runtime` on `sri-frontend`; historical extension runners and tests remain in place. Focused serving tests use `test_serving_*` names. This narrows the integration without deleting unrelated experimental code.
- The frontend demo currently initializes a catalog in a temporary store for its process lifetime. The standalone extension service supports a persistent store. This frozen-catalog check does not add a catalog-mutation HTTP endpoint to the frontend or qualify growth/load performance.
- Serving traces expose the canonical turn, explicit state, mapping score/margin, fallback reason, candidates, and catalog version. No Qwen server or external model API is used.

## Reproduction and retained evidence

Install API and semantic dependencies, obtain the original catalog, and set `SEARCH_MODEL_DIR` to the retained model root when needed. The local retained model path is also auto-detected by the frontend.

```sh
python -m unittest discover tests
python -m search_runtime.check_public --catalog data/catalog.jsonl
python -m tests.evaluate_frontend --catalog data/catalog.jsonl --output data/search/repro-api-public.json
python -m tests.evaluate_language --catalog data/catalog.jsonl --samples data/public_set.jsonl --templates tests/language_templates.json --bank data/releases/extension-v1/matrix/paraphrases/bank.json --store data/search/repro-store --output data/search/repro-wording.json --level wording --seed 20260910
```

Repeat the last command with `--level semantic` and a different output filename. Outputs refuse overwrite. Preserve the same bank/templates; do not tune on supposed sealed targets. The frontend endpoint harness is specific to `sri-frontend`.

Raw results: `data/search/verification-fixed-constrained.json`, `verification-api-public.json`, `verification-final-wording.json`, and `verification-final-semantic.json`. Initial and intermediate results remain alongside them. Every natural result retains customer turns, original evaluator turns, responses, candidates, state, and route traces. `docs/frozen-catalog-verification.json` contains compact metrics, scenario breakdowns, input/source hashes, environment, model hashes, and raw-file checksums. Raw transcripts and SQLite/vector stores stay local and are ignored by Git.

One seed was evaluated, with shared public targets. This is not a multi-seed sealed campaign, a user study, or production p99 qualification. Timings were collected during overlapping local verification processes and are not used to make deployment throughput claims. See `natural-language-mapping.md` for the exact algorithm and an observed conversion example.

The large frontend cleanup commit was rejected by automatic review. The final integration therefore preserves the old experiment tree and uses the isolated serving package. Its runtime code is identical to the verified `extension-updated` implementation except for package-qualified imports. The compact result manifests retain the original pre-relocation source hashes.

After package relocation, all 81 tests pass. `frontend-runtime-provenance.json` verifies that all 14 serving modules match `extension-updated` exactly after normalizing package-qualified imports. The 200-session HTTP evaluation preceded this mechanical relocation; the post-relocation API tests exercise the new package.
