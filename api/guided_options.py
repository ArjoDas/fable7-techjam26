from __future__ import annotations

import secrets
from collections import Counter
from typing import Any


def _option(
    label: str,
    message: str,
    kind: str,
    estimated_remaining: int | None = None,
) -> dict[str, Any]:
    return {
        "id": secrets.token_urlsafe(9),
        "label": label,
        "message_preview": message,
        "kind": kind,
        "estimated_remaining": estimated_remaining,
    }


def opening_options(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for category in categories[:8]:
        value = str(category["value"])
        label = str(category["label"])
        count = int(category["count"])
        options.append(
            _option(
                f"Explore {label}",
                f"I'm looking for {value}, but I'm still exploring.",
                "opening",
                count,
            )
        )
    return options


def follow_up_options(agent: Any, session_id: str) -> list[dict[str, Any]]:
    state = agent._sessions.get(session_id) or {}
    constraints = agent._constraint_phrases(state.get("messages"))
    ranking = list(state.get("last_ranking") or [])[:80]
    dialogue_index = agent._dialogue_index
    category = str(state.get("category_query") or "")
    next_values: Counter[str] = Counter()

    if dialogue_index is not None:
        depth = len(constraints)
        for asin in ranking:
            card = dialogue_index.cards.get(asin)
            if card is None or depth >= len(card.sequence):
                continue
            value = str(card.sequence[depth]).strip()
            if 1 < len(value) <= 90:
                next_values[value] += 1

    current_matches = int(state.get("last_dialogue_match_count") or len(ranking))
    candidates: list[tuple[float, str, int]] = []
    for value, support in next_values.items():
        exact_remaining = support
        if dialogue_index is not None and category:
            exact_remaining = len(
                dialogue_index.matching_prefix(category, [*constraints, value])
            )
        denominator = max(1, current_matches)
        balance = abs(0.5 - min(1.0, exact_remaining / denominator))
        candidates.append((balance, value, exact_remaining))
    candidates.sort(key=lambda row: (row[0], -row[2], row[1]))

    options = [
        _option(
            value[:46] + ("…" if len(value) > 46 else ""),
            f"For that, what matters is: {value}.",
            "constraint",
            remaining,
        )
        for _, value, remaining in candidates[:6]
    ]
    options.append(
        _option(
            "No additional preference",
            "I don't have an additional preference for other.",
            "no_preference",
            current_matches or None,
        )
    )
    if candidates and int(state.get("turn") or 0) > 0:
        _, value, remaining = candidates[-1]
        options.append(
            _option(
                "Change direction",
                f"Actually, ignore my earlier preference. What I need is: {value}.",
                "override",
                remaining,
            )
        )
    return options

