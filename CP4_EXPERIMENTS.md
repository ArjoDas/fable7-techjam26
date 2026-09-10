# Protected exposure experiments (CP7)

Baseline: `8a1047a3cdb54d73fa3db9ee5286cc5fcd5e5f5f`. Inputs and detailed local results: `data/releases/cp7/`.

| Change | HitRate | MRR | MTTC | TechnicalScore | Decision |
|---|---:|---:|---:|---:|---|
| Independent CP6 history + safe singleton/final-turn exposure | 1.0 | 1.0 | 2.07 | 0.9786 | Public improvement; paired acceptance pending |
| Exhaustion planner also protects singleton-only future exposures (batching still opt-in) | 1.0 | 1.0 | 2.07 | 0.9786 | Public unchanged; 30 tests pass; paired acceptance pending |
| Singleton promotion: public dev / synthetic dev / hard paired gates pass; disabled-policy parity passes all 3,300 cases | 1.0 | 1.0 | 2.07 | 0.9786 | Keep; final held-out confirmation pending |
