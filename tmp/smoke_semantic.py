import json
import time

from starter.agent import Agent
from api.products import ProductCatalog
from api.semantic import SemanticMapper
from api.examples import build_examples

t0 = time.perf_counter()
agent = Agent("data/catalog.jsonl", enable_trace=True)
print(f"agent built in {time.perf_counter()-t0:.1f}s")

t0 = time.perf_counter()
products = ProductCatalog("data/catalog.jsonl")
mapper = SemanticMapper(agent)
print(f"mapper built in {time.perf_counter()-t0:.1f}s; values={len(mapper.values)} cats={len(mapper.categories)} encoder={mapper.encoder is not None} err={mapper.encoder_error}")

t0 = time.perf_counter()
examples = build_examples(agent, products)
print(f"examples built in {time.perf_counter()-t0:.1f}s; count={len(examples)}")
for ex in examples:
    print(json.dumps({k: ex[k] for k in ('id','label','scenario','category','target_asin')}, ensure_ascii=False))
    for t in ex["turns"]:
        print("   S:", t["structured"])
        print("   N:", t["natural"])

for text, turn in [
    ("I need a durable leather belt for jeans", 1),
    ("just browsing for some comfy socks", 1),
    ("it should be black", 2),
    ("actually forget that, I want something waterproof", 2),
    ("nothing else, anything works", 3),
]:
    t0 = time.perf_counter()
    m = mapper.map(text, turn)
    print(f"--- {text!r} turn={turn} ({(time.perf_counter()-t0)*1000:.0f}ms)")
    print("    canonical:", m["canonical_message"])
    print("    category:", m["chosen_category"], m["category_candidates"][:2])
    print("    values:", [(v["value"], v["score"], v["semantic"]) for v in m["value_candidates"][:5]])
