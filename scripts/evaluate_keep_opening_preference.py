"""Public-set ablation: retain the opening preference on intent overrides."""

import hashlib
import inspect
import json
import textwrap
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter import agent as agent_module


def main():
    # Change exactly one statement, leaving override detection and coverage resets intact.
    source = textwrap.dedent(inspect.getsource(agent_module.Agent.respond))
    original = 'state["messages"] = [str(state["base_message"]), *disclosures, user_message]'
    replacement = 'state["messages"] = [*messages, user_message]'
    assert source.count(original) == 1
    namespace = {}
    exec(compile(source.replace(original, replacement), "<keep-opening-preference>", "exec"),
         vars(agent_module), namespace)
    variant = type("KeepOpeningPreferenceAgent", (agent_module.Agent,),
                   {"respond": namespace["respond"]})
    catalog = Path("data/catalog.jsonl")
    dataset = Path("data/public_set.jsonl")
    output = Path("data/releases/keep_opening_preference/results.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "change": {"original": original, "replacement": replacement},
        "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in (dataset, Path("starter/agent.py"), Path("evaluator/local_evaluator.py"))},
    }
    ids, categories, products = catalog_index(catalog)
    samples = load_jsonl(dataset)
    for name, cls in (("baseline", agent_module.Agent), ("keep_opening_preference", variant)):
        print(f"Running {name} on {len(samples)} public sessions", flush=True)
        agent = cls(catalog)
        try:
            report[name] = evaluate(agent, samples, ids, categories, products)
        finally:
            agent.connection.close()
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report[name].items() if k != "sessions"}, indent=2), flush=True)
    report["changed_sessions"] = [
        {"baseline": before, "keep_opening_preference": after}
        for before, after in zip(report["baseline"]["sessions"], report["keep_opening_preference"]["sessions"])
        if before != after
    ]
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Changed sessions: {len(report['changed_sessions'])}; report: {output}", flush=True)


if __name__ == "__main__":
    main()
