"""Curated example sessions with known targets for the pipeline visualization.

Each example scripts a full multi-turn conversation toward a specific target
product.  Targets are chosen so their dialogue-card prefix becomes unique
after the scripted disclosures, which guarantees the deterministic agent
hoists them to rank 1 - letting the UI trace the target through every stage.
"""
from __future__ import annotations

from typing import Any


# Explicit targets keep the public demo varied and stable as popularity changes.
# Each tuple is (ASIN, readable shopping label); clues still come from the index.
CURATED_TARGETS = (
    ("B016OT9D3K", "Graphic T-shirts"),
    ("B07S2Y3THP", "Canvas sneakers"),
    ("B08CZ34D75", "Running shoes"),
    ("B086ZNJY8K", "Walking shoes"),
    ("B07T9LRYRP", "Casual hoodies"),
    ("B07PS9NTSP", "Kids’ jeans"),
    ("B09DCLDB53", "Knit cardigans"),
    ("B082DM3N61", "Running socks"),
    ("B0BJVWCSKQ", "Bracelet watches"),
    ("B0725NL65K", "Sunglasses"),
    ("B005KGEMMQ", "Everyday wallets"),
    ("B09YCZSKRY", "Crossbody phone bags"),
)


def _prefix_count(index: Any, category: str, values: tuple[str, ...]) -> int:
    return len(index.prefixes.get((category, *values), ()))


def _natural_value(value: str) -> str:
    """Phrase a normalized catalog value naturally."""
    if value.startswith("color "):
        return f"color: {value.removeprefix('color ')}"
    return {"100 canvas": "100% canvas", "100 other fibers": "100% other fibers"}.get(value, value)


def _natural_category(category: str) -> str:
    """Restore catalog punctuation needed by the literal phrase matcher."""
    return (category.replace("t shirts", "t-shirts")
            .replace("hoodies sweatshirts", "hoodies & sweatshirts")
            .replace("sunglasses eyewear", "sunglasses & eyewear")
            .replace("card cases money", "card cases & money")
            .replace("handbags wallets", "handbags & wallets"))


def _pick_targets(agent: Any, per_category: int = 1, limit: int = 12) -> list[dict[str, Any]]:
    """Products whose 2-value prefix is unique but 1-value prefix is ambiguous."""
    index = agent._dialogue_index
    if index is None:
        return []
    picks: list[dict[str, Any]] = []
    used_categories: dict[str, int] = {}
    labels = dict(CURATED_TARGETS)
    curated = [(asin, index.cards[asin]) for asin in labels if asin in index.cards]
    # Small/custom catalogs can still demonstrate the pipeline using their own
    # products. The bundled catalog uses only the reviewed targets above.
    ordered = curated or sorted(
        index.cards.items(),
        key=lambda item: (-agent._popularity.get(item[0], 0.0), item[0]),
    )
    for asin, card in ordered:
        if len(picks) >= limit:
            break
        if len(card.sequence) < 2:
            continue
        category = card.category
        if used_categories.get(category, 0) >= per_category:
            continue
        first, second = card.sequence[0], card.sequence[1]
        if not (2 < len(first) <= 60 and 2 < len(second) <= 60):
            continue
        ambiguous = _prefix_count(index, category, (first,))
        unique = _prefix_count(index, category, (first, second))
        if not (2 <= ambiguous <= 80 and unique == 1):
            continue
        picks.append(
            {
                "asin": asin,
                "category": category,
                "label": labels.get(asin, category),
                "first": first,
                "second": second,
                "ambiguous_count": ambiguous,
            }
        )
        used_categories[category] = used_categories.get(category, 0) + 1
    return picks


def _other_value(agent: Any, category: str, avoid: str) -> str | None:
    """A plausible-but-wrong opening value from another product in category."""
    index = agent._dialogue_index
    ordered = sorted(
        index.cards.items(),
        key=lambda item: -agent._popularity.get(item[0], 0.0),
    )
    for _, card in ordered:
        if card.category != category or not card.sequence:
            continue
        value = card.sequence[0]
        if value != avoid and 2 < len(value) <= 60:
            if _prefix_count(index, category, (value,)) >= 2:
                return value
    return None


def build_examples(agent: Any, products: Any) -> list[dict[str, Any]]:
    picks = _pick_targets(agent, per_category=1, limit=12)
    examples: list[dict[str, Any]] = []

    def title(asin: str) -> str:
        card = products.cards.get(asin) or {}
        return str(card.get("title") or asin)

    for pick in picks[:4]:
        category, first, second = pick["category"], pick["first"], pick["second"]
        natural_category = _natural_category(category)
        examples.append(
            {
                "id": f"buying-{pick['asin']}",
                "label": f"Buying: {pick['label']}",
                "scenario": "buying",
                "category": category,
                "target_asin": pick["asin"],
                "target_title": title(pick["asin"]),
                "turns": [
                    {
                        "structured": f"I'm looking for {category}. A key requirement is: {first}.",
                        "natural": f"I need {natural_category} - {_natural_value(first)} is a must.",
                    },
                    {
                        "structured": f"For that, what matters is: {second}.",
                        "natural": f"It should also have {_natural_value(second)}.",
                    },
                ],
            }
        )

    for pick in picks[4:8]:
        category, first, second = pick["category"], pick["first"], pick["second"]
        natural_category = _natural_category(category)
        examples.append(
            {
                "id": f"browsing-{pick['asin']}",
                "label": f"Browsing: {pick['label']}",
                "scenario": "browsing",
                "category": category,
                "target_asin": pick["asin"],
                "target_title": title(pick["asin"]),
                "turns": [
                    {
                        "structured": f"I'm looking for {category}, but I'm still exploring.",
                        "natural": f"Just browsing for {natural_category}, not sure yet.",
                    },
                    {
                        "structured": f"For that, what matters is: {first}.",
                        "natural": f"I do care about {_natural_value(first)}.",
                    },
                    {
                        "structured": f"For that, what matters is: {second}.",
                        "natural": f"Also, {_natural_value(second)} matters to me.",
                    },
                ],
            }
        )

    for pick in picks[8:10]:
        category, first, second = pick["category"], pick["first"], pick["second"]
        natural_category = _natural_category(category)
        examples.append(
            {
                "id": f"rotation-{pick['asin']}",
                "label": f"Rotation: {pick['label']}",
                "scenario": "rotation",
                "category": category,
                "target_asin": pick["asin"],
                "target_title": title(pick["asin"]),
                "turns": [
                    {
                        "structured": f"I'm looking for {category}, but I'm still exploring.",
                        "natural": f"Just browsing for {natural_category}.",
                    },
                    {
                        "structured": f"For that, what matters is: {first}.",
                        "natural": f"What matters is {_natural_value(first)}.",
                    },
                    {
                        "structured": f"For that, what matters is: {first}.",
                        "natural": f"What matters is {_natural_value(first)}.",
                    },
                    {
                        "structured": f"For that, what matters is: {second}.",
                        "natural": f"And {_natural_value(second)} matters too.",
                    },
                ],
            }
        )

    for pick in picks[10:12]:
        category, first, second = pick["category"], pick["first"], pick["second"]
        natural_category = _natural_category(category)
        wrong = _other_value(agent, category, first)
        if wrong is None:
            continue
        examples.append(
            {
                "id": f"override-{pick['asin']}",
                "label": f"Override: {pick['label']}",
                "scenario": "override",
                "category": category,
                "target_asin": pick["asin"],
                "target_title": title(pick["asin"]),
                "turns": [
                    {
                        "structured": f"I'm looking for {category}. A key requirement is: {wrong}.",
                        "natural": f"I want {natural_category} with {_natural_value(wrong)}.",
                    },
                    {
                        "structured": f"Actually, ignore my earlier preference. What I need is: {first}.",
                        "natural": f"Actually, I prefer {_natural_value(first)} instead.",
                    },
                    {
                        "structured": f"For that, what matters is: {second}.",
                        "natural": f"Also, {_natural_value(second)}.",
                    },
                ],
            }
        )

    return examples
