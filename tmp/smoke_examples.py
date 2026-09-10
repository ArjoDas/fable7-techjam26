from starter.agent import Agent
from api.products import ProductCatalog
from api.semantic import SemanticMapper
from api.examples import build_examples
from starter.cp5_dialogue import message_is_protocol_compatible

agent = Agent("data/catalog.jsonl", enable_trace=True)
products = ProductCatalog("data/catalog.jsonl")
mapper = SemanticMapper(agent)
examples = build_examples(agent, products)

for variant in ("structured", "natural"):
    print(f"===== {variant} =====")
    for ex in examples:
        sid = f"{ex['id']}-{variant}"
        agent.reset(sid, {})
        target = ex["target_asin"]
        print(f"-- {ex['id']} target={target}")
        for turn, spec in enumerate(ex["turns"], start=1):
            message = spec[variant]
            if variant == "natural" and not message_is_protocol_compatible(message):
                mapping = mapper.map(message, turn)
                canonical = mapping.get("canonical_message")
                if canonical:
                    message = canonical
            result = agent.respond(sid, message, turn, 10)
            trace = agent._sessions[sid]["last_trace"]
            selected = trace["selection"]["selected"]
            rank = selected.index(target) + 1 if target in selected else None
            merged = trace["retrieval"]["candidate_asins"]
            in_pool = target in merged
            print(
                f"   t{turn}: decision={trace['selection']['decision']} k={len(selected)} "
                f"target_rank={rank} in_pool={in_pool} msg={message[:70]!r}"
            )
