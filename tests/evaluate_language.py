"""Retained public-task paraphrases, with the official simulator and scorer unchanged.

Run as python -m tests.evaluate_language (or via runpy when tests is not a package).
The adapter is evaluation-only: the serving wrapper receives only rendered text.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from search_runtime.catalog import Catalog
from search_runtime.events import decode
from search_runtime.factory import create


class RenderedAgent:
    def __init__(self, agent, samples, templates, bank, level, seed):
        self.agent, self.samples, self.templates, self.bank = (
            agent,
            samples,
            templates,
            bank,
        )
        self.level, self.seed, self.index = level, seed, -1
        self.turns = []
        self.sid = None

    def reset(self, sid, profile):
        if self.sid:
            self.agent.close(self.sid)
        self.sid = sid
        self.index += 1
        self.agent.reset(sid, profile)
        self.eligible = self.samples[self.index]["scenario_type"] != "intent_override"
        if self.index % 20 == 0:
            print(f"{self.level}: {self.index}/{len(self.samples)}", flush=True)

    def respond(self, sid, original, turn, top_k):
        event = decode(original)
        sample = self.samples[self.index]
        if event.kind == "override":
            self.eligible = True
        key = json.dumps(
            [sample["sample_id"], self.seed, asdict(event)], sort_keys=True
        )
        choice = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        missing = []

        def phrase(value):
            options = self.bank.get(value, []) if self.level == "semantic" else []
            if self.level == "semantic" and not options:
                missing.append(value)
            return options[choice % len(options)] if options else value

        message = original
        if self.level != "constrained":
            options = self.templates[event.kind]
            message = options[choice % len(options)].format(
                category=phrase(event.category) if event.category else "",
                values="; ".join(phrase(v) for v in event.values),
                attribute=event.attribute,
            )
        began = time.perf_counter()
        error = None
        try:
            response = self.agent.respond(sid, message, turn, top_k)
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)
            response = {"message": "", "ask_attribute": None, "recommendations": []}
        self.turns.append(
            {
                "sample_id": sample["sample_id"],
                "turn": turn,
                "canonical": original,
                "rendered": message,
                "literal_fallbacks": missing,
                "eligible": self.eligible,
                "response": response,
                "trace": self.agent.trace.get(sid, {}),
                "error": error,
                "ms": (time.perf_counter() - began) * 1000,
            }
        )
        return response


def main():
    p = argparse.ArgumentParser()
    for name in ("catalog", "samples", "templates", "bank", "store", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument(
        "--level", choices=["constrained", "wording", "semantic"], required=True
    )
    p.add_argument("--seed", type=int, default=20260910)
    args = p.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError("Do not overwrite retained results")
    ids, categories, products = catalog_index(args.catalog)
    assert len(ids) == len(products) == 50000
    samples = load_jsonl(args.samples)
    templates = json.loads(Path(args.templates).read_text(encoding="utf-8"))
    bank = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    source_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path("search_runtime").glob("*.py")
    }
    store = Catalog(args.store, args.catalog)
    try:
        agent = create(store, "minilm")
        adapter = RenderedAgent(agent, samples, templates, bank, args.level, args.seed)
        result = evaluate(adapter, samples, ids, categories, products)
        result["hit_by_turn5"] = sum(
            s["hit"] and s["first_hit_turn"] <= 5 for s in result["sessions"]
        ) / len(samples)
        targets = {s["sample_id"]: s["ground_truth"]["parent_asin"] for s in samples}
        recalled = {
            t["sample_id"]
            for t in adapter.turns
            if t["eligible"]
            and t["turn"] <= 5
            and targets[t["sample_id"]] in t["trace"].get("candidate_ids", [])
        }
        result["recall100_by_turn5"] = len(recalled) / len(samples)
        result["route_counts"] = dict(
            Counter(t["trace"].get("route") for t in adapter.turns)
        )
        result["model_calls"] = agent.model_calls
        result["errors"] = sum(t["error"] is not None for t in adapter.turns)
        result["literal_fallback_turns"] = sum(
            bool(t["literal_fallbacks"]) for t in adapter.turns
        )
        result["turns"] = adapter.turns
        result["manifest"] = {
            "config": vars(args),
            "catalog_size": len(ids),
            "label": (
                "official compatibility"
                if args.level == "constrained"
                else "experimental public-task paraphrases (historical targets)"
            ),
            "input_hashes": {
                name: hashlib.sha256(Path(getattr(args, name)).read_bytes()).hexdigest()
                for name in ("catalog", "samples", "templates", "bank")
            },
            "source_hashes": source_hashes,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2))
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("turns", "sessions", "manifest")
                },
                indent=2,
            ),
            flush=True,
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
