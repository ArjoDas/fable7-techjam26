"""Compare BM25 route ablations, preserving other ranking lanes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter.agent import Agent


class ConjunctiveOnlyAgent(Agent):
    phrase_weight = 0.0

    def _fused_search(
        self, terms, top_k, disjunctive_weight=1.0, popularity_weight=0.0,
        route_limit=150, category=None,
    ):
        if not terms:
            return []
        expressions = [(" AND ".join(f'"{term}"' for term in terms), 2.5)]
        if self.phrase_weight:
            expressions.append((
                " OR ".join(
                    f'"{terms[index]} {terms[index + 1]}"'
                    for index in range(len(terms) - 1)
                ), self.phrase_weight,
            ))
        ranks = {}
        scores = {}
        for expression, weight in expressions:
            if not expression:
                continue
            for rank, asin in enumerate(
                self._ranked_asins(expression, route_limit, category), start=1,
            ):
                ranks[asin] = min(ranks.get(asin, rank), rank)
                scores[asin] = scores.get(asin, 0.0) + weight / (20.0 + rank)
        if category and not scores:
            return self._fused_search(
                terms, top_k, disjunctive_weight, popularity_weight,
                route_limit, category=None,
            )
        if popularity_weight > 0.0:
            popularity_ranking = sorted(
                scores, key=lambda asin: (-self._popularity.get(asin, 0.0), asin),
            )
            for rank, asin in enumerate(popularity_ranking, start=1):
                scores[asin] += popularity_weight / (20.0 + rank)
        return sorted(scores, key=lambda asin: (-scores[asin], ranks[asin], asin))[:top_k]


class OrDisabledAgent(ConjunctiveOnlyAgent):
    phrase_weight = 1.25


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["conjunctive_only", "or_disabled"], default="conjunctive_only")
    parser.add_argument("--baseline-report", type=Path, help="Reuse a baseline from the same commit and datasets")
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog.jsonl"))
    parser.add_argument("--datasets", nargs="+", type=Path, default=[
        Path("data/public_set.jsonl"),
        Path("data/releases/cp4/synthetic_dev.jsonl"),
        Path("data/releases/cp4/hard_cases.jsonl"),
    ])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.output = args.output or Path(f"data/releases/{args.variant}/results.json")
    variant_class = ConjunctiveOnlyAgent if args.variant == "conjunctive_only" else OrDisabledAgent
    report = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "experiment_weights": {"conjunctive": 2.5, "phrase": variant_class.phrase_weight, "disjunctive": 0.0},
        "notes": "Disabled routes contribute no candidates. All other Agent defaults retained.",
        "datasets": {},
    }
    if args.baseline_report:
        prior = json.loads(args.baseline_report.read_text())
        if prior["commit"] != report["commit"]:
            raise ValueError("Baseline commit mismatch")
        for dataset in args.datasets:
            entry = prior["datasets"][str(dataset)]
            if entry["sha256"] != hashlib.sha256(dataset.read_bytes()).hexdigest():
                raise ValueError(f"Baseline dataset mismatch: {dataset}")
            report["datasets"][str(dataset)] = {
                "sha256": entry["sha256"], "baseline": entry["baseline"],
            }
        report["baseline_source"] = str(args.baseline_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    catalog_ids, categories, products = catalog_index(args.catalog)
    variants = [] if args.baseline_report else [("baseline", Agent)]
    variants.append((args.variant, variant_class))
    for name, agent_class in variants:
        agent = agent_class(args.catalog)
        for dataset in args.datasets:
            print(f"Running {name}: {dataset}", flush=True)
            samples = load_jsonl(dataset)
            start = time.perf_counter()
            result = evaluate(agent, samples, catalog_ids, categories, products)
            result.pop("sessions")
            result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
            entry = report["datasets"].setdefault(str(dataset), {
                "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            })
            entry[name] = result
            if "baseline" in entry and args.variant in entry:
                entry["delta"] = {
                    key: round(entry[args.variant][key] - entry["baseline"][key], 6)
                    for key in ["hit_rate_at_10", "mrr", "mttc", "efficiency", "recommended_technical_score"]
                }
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({"variant": name, "dataset": str(dataset), **result}), flush=True)
        agent.connection.close()
        del agent


if __name__ == "__main__":
    main()
