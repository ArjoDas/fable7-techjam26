"""Output improvements that preserve the independent CP6 reference trajectory.

Only the published deterministic continuation protocol proves a miss. Ordinary
conversation, skipped turns, and pre-override exposures do not establish one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from starter.cp5_dialogue import normalize_protocol_text


@dataclass
class ExposureHistory:
    compatible: bool = True
    eligible: bool = False
    exhausted: bool = False
    last_turn: int = 0
    pending: tuple[str, ...] = ()
    refuted: set[str] = field(default_factory=set)

    def observe(self, message: str, turn: int, known_category: bool) -> None:
        text = normalize_protocol_text(message)
        if turn != self.last_turn + 1:
            self.compatible = False
        override = re.fullmatch(
            r"Actually, ignore my earlier preference\. What I need is: .+\.", text
        ) is not None
        if turn == 1:
            browsing = re.fullmatch(r"I'm looking for .+, but I'm still exploring\.", text)
            buying = re.fullmatch(r"I'm looking for .+\. A key requirement is: .+\.", text)
            tentative = re.fullmatch(r"I'm looking for .+\. .+", text)
            self.compatible &= known_category and bool(browsing or buying or tentative)
            self.eligible = bool(browsing or buying)
        elif override:
            self.refuted.clear()
            self.pending = ()
            self.eligible = True
            self.exhausted = False
        else:
            disclosure = re.fullmatch(r"For that, what matters is: .+\.", text)
            boundary = text == "I don't have a preference for other; please use your judgment."
            exhausted = text == "I don't have an additional preference for other."
            self.compatible &= bool(disclosure or boundary or exhausted)
            if self.compatible and self.eligible:
                self.refuted.update(self.pending)
                self.exhausted = exhausted
        self.last_turn = turn

    @property
    def active(self) -> bool:
        return self.compatible and self.eligible


def protect_output(
    reference: list[str], ranked: list[str], cohort: list[str],
    history: ExposureHistory, turn: int, top_k: int, *,
    singleton: bool, batching: bool, future_reference: set[str],
) -> list[str]:
    """Replace refuted probes; only append products outside CP6's future hits."""
    selected = list(reference)
    if not history.active or top_k <= 0:
        return selected
    pool = list(dict.fromkeys([*cohort, *ranked]))
    if singleton and len(selected) == 1 and selected[0] in history.refuted:
        replacement = next((a for a in pool if a not in history.refuted), None)
        if replacement is not None:
            selected = [replacement]
    if singleton and turn == 10:
        # No future hit can be harmed by filling the final slate. Preserve the
        # relative order of all still-possible reference hits before appending.
        selected = [a for a in selected if a not in history.refuted]
        selected.extend(a for a in pool if a not in history.refuted and a not in selected)
        return selected[:top_k]
    if batching and history.exhausted and turn < 10:
        # A product due at rank one later must never end the session at rank
        # two now. Only candidates CP6 would miss entirely can occupy extras.
        selected.extend(a for a in cohort if a not in future_reference
                        and a not in history.refuted and a not in selected)
    return selected[:top_k]
