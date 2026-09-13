"""Capture public example sessions for the static frontend (never run at build time).

Usage: SEARCH_MODEL_DIR=/path/to/models python -m scripts.record_demo \
    --model-revision <Hugging-Face-commit>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from api.models import TurnResponse
from api.runtime import AgentRuntime
from search_runtime.common import MODEL_CACHE, ROOT, sha256
from search_runtime.models import Embeddings


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


async def capture(args: argparse.Namespace) -> None:
    catalog = Path(args.catalog).resolve()
    output = Path(args.output).resolve()
    model_files = [MODEL_CACHE / "minilm" / name for name in
                   ("tokenizer.json", "onnx/model_quint8_avx2.onnx")]
    for path in model_files:
        if not path.is_file():
            raise SystemExit(f"Missing {path}. Set SEARCH_MODEL_DIR; the recorder does not download models.")
    runtime = AgentRuntime(catalog)
    runtime.start()
    await runtime._initialization_task
    if runtime.status != "ready":
        await runtime.shutdown()
        raise SystemExit(runtime.error)
    sessions = {}
    examples = []
    try:
        def warm_encoder():
            encoder = Embeddings()
            encoder.encode(["recording warmup"])
            runtime.wrapper.converter.matcher.encoder = encoder
        await runtime._submit(warm_encoder)
        for example in runtime.examples:
            slug = re.sub(r"[^a-z0-9]+", "-", example["label"].split(": ", 1)[1].lower()).strip("-")
            exported = {**example, "id": slug, "engine_example_id": example["id"], "recordings": {}}
            for mode in ("structured", "natural"):
                sid = f"recorded-{slug}-{mode}"
                await runtime.reset(sid, {})
                turns = []
                methods = []
                for number, turn in enumerate(example["turns"], 1):
                    result = await runtime.respond(sid, turn[mode], number, include_trace=True, semantic=mode == "natural")
                    response = TurnResponse(session_id=sid, mode="demo", turn=number, max_turns=10,
                                            **result).model_dump(exclude={"message_options"})
                    trace = response["trace"]
                    if trace is None:
                        raise ValueError(f"Missing trace: {sid}, turn {number}")
                    extension = trace.get("extension", {})
                    if extension.get("fallback_reason"):
                        raise ValueError(f"Unexpected fallback: {sid}, turn {number}: {extension['fallback_reason']}")
                    method = "protocol" if mode == "structured" else ("minilm" if trace.get("semantic", {}).get("encoder_used") else "literal")
                    methods.append(method)
                    turns.append({"turn": number, "input": turn[mode], "response": response})
                if turns[-1]["response"]["recommendations"][0]["parent_asin"] != example["target_asin"]:
                    raise ValueError(f"Target did not finish first: {sid}")
                if example["scenario"] == "rotation" and not any(t["response"]["trace"]["selection"]["decision"] == "rotation" for t in turns):
                    raise ValueError(f"Missing rotation: {sid}")
                filename = f"{slug}.{mode}.json"
                recording = {"schema_version": 1, "example_id": slug, "mode": mode, "turns": turns}
                sessions[filename] = recording
                exported["recordings"][mode] = {"file": filename, "matching": methods}
                await runtime.remove(sid)
                print(f"{slug:24} {mode:10} {len(turns)} turns {', '.join(methods)}", flush=True)
            examples.append(exported)
    finally:
        await runtime.shutdown()
    if len(examples) < 10 or len({e['id'] for e in examples}) != len(examples):
        raise ValueError("Need at least ten uniquely named examples")
    # Hash the actual runtime source as well as recording its containing commit.
    source_files = sorted(p for folder in ("api", "starter", "search_runtime", "evaluator")
                          for p in (ROOT / folder).rglob("*.py"))
    source_digest = hashlib.sha256()
    for path in source_files:
        source_digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    provenance = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source_repository": "https://github.com/ArjoDas/fable7-techjam26",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime_source_sha256": source_digest.hexdigest(),
        "catalog_sha256": sha256(catalog), "catalog_size": runtime.catalog_size,
        "model": {"repository": "sentence-transformers/all-MiniLM-L6-v2", "revision": args.model_revision,
                  "files": {str(p.relative_to(MODEL_CACHE)): sha256(p) for p in model_files}},
    }
    # Only publish files after all sessions have passed validation.
    for name, recording in sessions.items():
        write_json(output / name, recording)
    write_json(output / "manifest.json", {"schema_version": 1, "provenance": provenance, "examples": examples})
    total = sum((output / name).stat().st_size for name in [*sessions, "manifest.json"])
    print(f"Saved {len(sessions)} sessions ({sum(len(s['turns']) for s in sessions.values())} turns), {total:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(ROOT / "data/catalog.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "web/public/recordings"))
    parser.add_argument("--model-revision", required=True, help="Pinned source revision of the provided model files")
    asyncio.run(capture(parser.parse_args()))
