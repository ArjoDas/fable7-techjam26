# CP7: protecting CP6 outcomes while improving coverage

The output policy keeps CP6's hypothetical `shown` set and signature independent
from actual recommendations. `safe_exposure` records actual exposures, eligible
continuations, and confirmed misses. The retrieval routes, learned weights,
original prefix lookup, and `other` question policy are unchanged.

An eligible continuation refutes only the actual previous slate. Recommendations
before an intent override do not establish misses; the override clears actual
exposure memory. Unknown wording or nonconsecutive turns permanently disables the
extra policy for that session. Boundary refusal is not evidence exhaustion.

## Measured results

| Suite | CP6 score | CP7 score | CP6 MTTC | CP7 MTTC | Regressions |
|---|---:|---:|---:|---:|---:|
| Public 200 | 0.978000 | 0.978600 | 2.100 | 2.070 | 0 |
| synthetic_dev | 0.970712 | 0.972667 | 2.400 | 2.330 | 0 |
| hard | 0.815892 | 0.854222 | 4.302 | 4.002 | 0 |
| synthetic_holdout | 0.970855 | 0.972570 | 2.446 | 2.364 | 0 |
| fresh_weighted | 0.965300 | 0.969688 | 2.535 | 2.450 | 0 |
| fresh_uniform | 0.946300 | 0.953589 | 2.835 | 2.750 | 0 |
| paraphrase | 0.881066 | 0.881066 | 2.070 | 2.070 | 0 |

Public HitRate@10 and MRR remain 1.0. Hard-set hit rate improves from
0.856 to 0.912 (28 recovered misses). Across 3,300 cases, 214 sessions improve
and 342 turns are saved, with zero per-session regressions against CP6 or the
singleton-only policy. Disabled-policy responses match the independent baseline
exactly on every suite. All agents report zero exceptions; 33 unit tests pass.
Paraphrase results are unofficial; its complete response digest is unchanged.

The [aggregate validation artifact](cp7_validation.json) includes hashes, scenario
metrics, paired comparisons, and isolated batching ablations. Holdout results
were confirmed after freezing the policy; no holdout cases were used to tune it.

## Protection argument

Under the published simulator, the next customer disclosure depends on the
question and disclosed values, not on the recommended IDs. Keeping the question
unchanged therefore permits an independent CP6 trajectory until the first hit.

1. An unrefuted CP6 singleton is preserved. A refuted singleton cannot be the
   target; replacing it can only produce an earlier rank-one hit or another miss.
2. Before turn 10, ordinary multi-product CP6 slates retain their order.
3. On turn 10, removing actual confirmed misses cannot lower a remaining target's
   rank. New candidates follow the remaining reference candidates.
4. After an explicit exhausted `other` reply, the query and ranking stay fixed.
   A copy of selection state can enumerate every future CP6 output through turn
   10. Candidates absent from all those outputs would be CP6 misses; only these
   candidates may be appended in spare positions before the final turn.
5. The combined policy also protects the singleton-only policy's future outputs.
   Thus batching cannot replace a later singleton-only success with an earlier
   lower-rank hit. Both rollouts use copies of mutable exposure sets.

The auxiliary cohort spans the full matching catalog prefix, without the
reference ranking's 80-product cap. It deduplicates normalized observed fragments
in the same way as catalog sequences. This fixes auxiliary lookup for equivalent
phrases such as `color: black` and `color-black`, while retaining the original
reference behavior exactly when both new flags are disabled.

These guarantees assume the published deterministic protocol and fixed evaluator
turn/top-k limits. They do not infer explicit rejection from arbitrary real-user
conversation or promise semantic robustness on unseen free-form wording.

## Reproduction and acceptance

Run commands from the repository root. The catalog and existing CP4 datasets must
be installed first, as described in `README_DEV.md`.

```bash
# Once: pin baseline source/weights, input hashes, and two fresh 200-target suites.
python3 -m scripts.evaluate_cp7 --freeze

# Develop and ablate on development data only.
python3 -m scripts.evaluate_cp7 --variants reference,singleton,batching,combined \
  --suites public_dev,synthetic_dev,hard

# After freezing the policy, confirm without inspecting holdout failures.
python3 -m scripts.evaluate_cp7 --variants reference,singleton \
  --suites public_holdout,synthetic_holdout,fresh_weighted,fresh_uniform,paraphrase
python3 -m scripts.evaluate_cp7 --variants combined --compare-to singleton \
  --suites public_dev,synthetic_dev,hard,public_holdout,synthetic_holdout,fresh_weighted,fresh_uniform,paraphrase

python3 -m unittest discover tests
python3 -m evaluator.local_evaluator
```

The independent baseline is loaded from commit
`8a1047a3cdb54d73fa3db9ee5286cc5fcd5e5f5f`, including its original helper and
weights. No evaluator code, frozen source, or result labels are loaded by the
runtime agent. `--freeze` refuses to overwrite an existing manifest. Subsequent
runs verify all frozen input hashes before evaluation.

Per-session comparisons require nondecreasing hit and reciprocal rank, and
nonincreasing first-hit turn (miss = 11). Comparisons use the unrounded session
values. Reference parity additionally hashes every input message and response,
not merely the final metrics. The runner fails on regressions, response-parity
violations, or exceptions swallowed by the official evaluator.

Detailed local outcomes remain under ignored `data/releases/cp7/`; console output
contains only aggregates and regression counts, including for holdouts. Fresh
weighted and uniform targets are mutually disjoint and exclude public, synthetic
train/dev/holdout, and hard-set targets. Paraphrase results are unofficial and
must be compared only to the corresponding CP6 paraphrase baseline.

Constructor ablations: `use_safe_refutation` controls singleton replacement and
final-turn filling; `use_safe_exhaustion` controls protected early batching.
Passing both as `False` reproduces CP6's output policy.
