"""Paired CP7 regression checks. Labels and frozen source are offline-only.

Freeze once before changing the agent; holdout output is aggregate-only.
Detailed results live in ignored data/releases/cp7, never in runtime assets.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import subprocess
import types
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from scripts.create_cp3_synthetic_set import weighted_sample_without_replacement
from scripts.create_cp4_synthetic_sets import scenario_assignment
from tests.paraphrase_harness import run as paraphrase_run

ROOT = Path("data/releases/cp7")
BASELINE_COMMIT = "8a1047a3cdb54d73fa3db9ee5286cc5fcd5e5f5f"
SUITES = {
    "public_dev": "data/public_set.jsonl",
    "public_holdout": "data/public_set.jsonl",
    "synthetic_dev": "data/releases/cp4/synthetic_dev.jsonl",
    "hard": "data/releases/cp4/hard_cases.jsonl",
    "synthetic_holdout": "data/releases/cp4/synthetic_holdout.jsonl",
    "fresh_weighted": str(ROOT / "fresh_weighted.jsonl"),
    "fresh_uniform": str(ROOT / "fresh_uniform.jsonl"),
    "paraphrase": "data/public_set.jsonl",
}
VARIANTS = {
    "reference": (False, False),
    "singleton": (True, False),
    "batching": (False, True),
    "combined": (True, True),
}


def digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def freeze() -> None:
    if (ROOT / "manifest.json").exists():
        raise SystemExit("Already frozen; do not overwrite the acceptance suite.")
    original_evaluator = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:evaluator/local_evaluator.py"], text=True,
    )
    if ast.dump(ast.parse(original_evaluator)) != ast.dump(ast.parse(
        Path("evaluator/local_evaluator.py").read_text()
    )):
        raise SystemExit("Evaluator behavior differs from the official baseline")
    ROOT.mkdir(parents=True, exist_ok=True)
    excluded = set()
    for path in set(SUITES.values()) | {"data/releases/cp4/synthetic_train.jsonl"}:
        if Path(path).exists():
            excluded.update(str(s["ground_truth"]["parent_asin"]) for s in load_jsonl(path))
    products = load_jsonl("data/catalog.jsonl")
    eligible = [p for p in products if p["parent_asin"] not in excluded]
    weighted = weighted_sample_without_replacement(
        [(p["parent_asin"], max(0.0, float(p.get("rating_number") or 0))) for p in eligible],
        200, 20260911,
    )
    weighted_set = set(weighted)
    uniform = random.Random(20260912).sample(
        sorted(p["parent_asin"] for p in eligible if p["parent_asin"] not in weighted_set), 200,
    )
    for name, targets in (("fresh_weighted", weighted), ("fresh_uniform", uniform)):
        scenarios = scenario_assignment(len(targets), 20260913)
        rows = [{"sample_id": f"{name}_{i:04d}", "scenario_type": scenarios[i],
                 "ground_truth": {"parent_asin": asin}, "user_profile": {}}
                for i, asin in enumerate(targets)]
        Path(SUITES[name]).write_text("".join(json.dumps(r) + "\n" for r in rows))
    for name in ("agent.py", "cp5_dialogue.py", "reranker_weights.json"):
        data = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:starter/{name}"])
        (ROOT / name).write_bytes(data)
    paths = set(SUITES.values()) | {"data/catalog.jsonl", "data/cp2_split.json",
        "evaluator/local_evaluator.py", "tests/paraphrase_harness.py",
        "data/releases/cp4/synthetic_train.jsonl"}
    paths.update(str(ROOT / n) for n in ("agent.py", "cp5_dialogue.py", "reranker_weights.json"))
    write_json(ROOT / "manifest.json", {
        "baseline_commit": BASELINE_COMMIT, "seeds": [20260911, 20260912, 20260913],
        "hashes": {p: digest(p) for p in sorted(paths)},
        "baseline_settings": "Agent constructor defaults at baseline_commit",
    })


def frozen_agent():
    # Rewrite just the helper import so later helper edits cannot alter CP6.
    import sys
    helper = types.ModuleType("_cp7_frozen_dialogue")
    sys.modules[helper.__name__] = helper
    exec(compile((ROOT / "cp5_dialogue.py").read_text(), str(ROOT / "cp5_dialogue.py"), "exec"), helper.__dict__)
    module = types.ModuleType("_cp7_frozen_agent")
    module.__file__ = str(ROOT / "agent.py")
    source = (ROOT / "agent.py").read_text().replace("from starter.cp5_dialogue import", "from _cp7_frozen_dialogue import")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module.Agent()


class Recorder:
    def __init__(self, agent):
        self.agent = agent
        self.hash = hashlib.sha256()
        self.errors = 0

    def reset(self, session_id, profile):
        # These suites run sequentially; discard completed session state.
        self.agent._sessions.clear()
        self.agent.reset(session_id, profile)

    def respond(self, session_id, message, turn, top_k):
        try:
            result = self.agent.respond(session_id, message, turn, top_k)
        except Exception:
            self.errors += 1
            raise
        self.hash.update(json.dumps([message, turn, top_k, result], sort_keys=True).encode())
        return result


def compare(before: dict, after: dict) -> dict:
    old = {s["sample_id"]: s for s in before["sessions"]}
    new = {s["sample_id"]: s for s in after["sessions"]}
    if set(old) != set(new) or len(old) != len(before["sessions"]) or len(new) != len(after["sessions"]):
        raise ValueError("Session identities must match uniquely")
    regressions = gains = turns_saved = 0
    for key, b in old.items():
        a = new[key]
        bt, at = b["first_hit_turn"] or 11, a["first_hit_turn"] or 11
        bad = a["hit"] < b["hit"] or a["reciprocal_rank"] < b["reciprocal_rank"] or at > bt
        regressions += int(bad)
        gains += int(not bad and (a["hit"] > b["hit"] or a["reciprocal_rank"] > b["reciprocal_rank"] or at < bt))
        turns_saved += bt - at
    return {"regressions": regressions, "improved_sessions": gains, "turns_saved": turns_saved}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--variants", default="baseline")
    parser.add_argument("--suites", default=",".join(SUITES))
    parser.add_argument("--compare-to", default="baseline")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for path, expected in manifest["hashes"].items():
        if digest(path) != expected:
            raise SystemExit(f"Frozen input changed: {path}")
    ids, categories, products = catalog_index("data/catalog.jsonl")
    split = json.loads(Path("data/cp2_split.json").read_text())
    failures = 0
    for variant in args.variants.split(","):
        if variant == "baseline":
            agent = frozen_agent()
        else:
            from starter.agent import Agent
            single, batch = VARIANTS[variant]
            agent = Agent(use_safe_refutation=single, use_safe_exhaustion=batch)
        for suite in args.suites.split(","):
            samples = load_jsonl(SUITES[suite])
            if suite in ("public_dev", "public_holdout"):
                selected = set(split["dev_ids" if suite == "public_dev" else "holdout_ids"])
                samples = [s for s in samples if s["sample_id"] in selected]
            recorder = Recorder(agent)
            result = (paraphrase_run(recorder, samples, ids, categories, products, paraphrase=True)
                      if suite == "paraphrase" else evaluate(recorder, samples, ids, categories, products))
            result["response_digest"] = recorder.hash.hexdigest()
            result["agent_exceptions"] = recorder.errors
            record = {k: v for k, v in result.items() if k != "sessions"}
            record.update(variant=variant, suite=suite)
            if variant != "baseline":
                for comparator in dict.fromkeys(["baseline", *args.compare_to.split(",")]):
                    before = json.loads((ROOT / comparator / f"{suite}.json").read_text())
                    comparison = compare(before, result)
                    record[f"vs_{comparator}"] = comparison
                    failures += comparison["regressions"]
                    if variant == "reference":
                        equal = before["response_digest"] == result["response_digest"]
                        record["exact_response_parity"] = equal
                        failures += int(not equal)
            failures += recorder.errors
            write_json(ROOT / variant / f"{suite}.json", result)
            write_json(ROOT / variant / f"{suite}_summary.json", record)
            print(json.dumps(record), flush=True)
        agent.connection.close()
    if failures:
        raise SystemExit(f"FAILED: {failures} regression/parity/exception violations")


if __name__ == "__main__":
    main()
