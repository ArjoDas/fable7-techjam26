"""Local phrase matching and explicit shopping state; no generative services."""

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass, field


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold().replace("&", " and ")))


class PhraseMatcher:
    """Lazy MiniLM, persisted text cache, bounded active-evidence comparisons.

    Deleted evidence stays cached but is never a candidate. Identical evidence
    on reintroduction reuses its vector; weights never change. Cold encoding is
    synchronous: the deadline prevents further batches, not an in-flight batch.
    """

    def __init__(self, directory, encoder=None, threshold=0.65, margin=0.05):
        self.path = directory / "phrase-vectors.sqlite"
        self.encoder = encoder
        self.threshold, self.margin = threshold, margin
        self.encoded = 0
        self.calls = 0
        self.last = None

    def _vectors(self, texts, deadline):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY, vector BLOB)"
            )
            return self._cached_vectors(texts, deadline, db)

    def _cached_vectors(self, texts, deadline, db):
        import numpy as np
        from search_runtime.common import MODEL_CACHE

        # Separate caches for different local ONNX files, including replacements.
        model = MODEL_CACHE / "minilm/onnx/model_quint8_avx2.onnx"
        stamp = (
            (str(model), model.stat().st_size, model.stat().st_mtime_ns)
            if model.exists()
            else ("injected",)
        )
        keys = [
            hashlib.sha256((str(stamp) + text).encode()).hexdigest() for text in texts
        ]
        values = {}
        missing = []
        for key, text in zip(keys, texts):
            row = db.execute(
                "SELECT vector FROM vectors WHERE key=?", (key,)
            ).fetchone()
            if row:
                values[key] = np.frombuffer(row[0], dtype="float32")
            elif key not in {k for k, _ in missing}:
                missing.append((key, text))
        for offset in range(0, len(missing), 16):
            if time.perf_counter() >= deadline:
                raise TimeoutError("MiniLM phrase deadline")
            if self.encoder is None:
                from search_runtime.models import Embeddings

                self.encoder = Embeddings()
            batch = missing[offset : offset + 16]
            self.calls += 1
            vectors = self.encoder.encode([text for _, text in batch])
            for (key, _), vector in zip(batch, vectors):
                vector = np.asarray(vector, dtype="float32")
                values[key] = vector
                db.execute(
                    "INSERT OR REPLACE INTO vectors VALUES (?,?)",
                    (key, vector.tobytes()),
                )
                self.encoded += 1
            db.commit()
        return np.stack([values[key] for key in keys])

    def match(self, phrase, candidates, deadline):
        self.last = None
        candidates = sorted(set(candidates))
        # The evaluator may expose both 'blue' and 'color: blue'. Counting
        # these as competing meanings would cause false margin abstentions.
        candidates = [
            v
            for v in candidates
            if not (
                ":" in v
                and v.split(":", 1)[1].strip() in candidates
                and attribute(v) == attribute(v.split(":", 1)[1].strip())
            )
        ]
        exact = [v for v in candidates if normalized(v) == normalized(phrase)]
        if exact:
            return exact[0]
        if not candidates:
            return None
        # Do not normalize away quantities or invert polarity.
        numbers = re.findall(r"\d+(?:\.\d+)?", phrase)
        candidates = [
            v for v in candidates if re.findall(r"\d+(?:\.\d+)?", v) == numbers
        ]
        if not candidates:
            return None
        candidates = candidates[:256]
        vectors = self._vectors([phrase, *candidates], deadline)
        if time.perf_counter() >= deadline:
            raise TimeoutError("MiniLM phrase deadline")
        scores = vectors[1:] @ vectors[0]
        order = scores.argsort()[::-1]
        score = float(scores[order[0]])
        margin = score - float(scores[order[1]]) if len(order) > 1 else 1.0
        self.last = {
            "phrase": phrase,
            "value": candidates[order[0]],
            "score": score,
            "margin": margin,
        }
        if score >= self.threshold and margin >= self.margin:
            return candidates[order[0]]
        return None


def attribute(value):
    text = normalized(value)
    if ":" in value:
        return normalized(value.split(":", 1)[0])
    for key in ("color", "material", "size", "brand", "price", "style", "fit"):
        if text.startswith(key + " "):
            return key
    if text in {
        "red",
        "blue",
        "black",
        "white",
        "green",
        "pink",
        "yellow",
        "navy",
        "grey",
        "gray",
    }:
        return "color"
    if re.fullmatch(
        r"(?:\d+ )?(cotton|polyester|linen|silk|wool|leather|nylon|denim)", text
    ):
        return "material"
    return "evidence:" + text


@dataclass
class Constraint:
    attribute: str
    value: str
    negative: bool
    turn: int


@dataclass
class ShoppingState:
    category: str = ""
    mode: str = "buying"
    constraints: list = field(default_factory=list)
    history: list = field(default_factory=list)
    event: str = "opening"

    def put(self, value, negative, turn, replace=False):
        key = attribute(value)
        removed = [
            c
            for c in self.constraints
            if c.value == value
            or (replace and not negative and not c.negative and c.attribute == key)
        ]
        self.history.extend({**asdict(c), "replaced_at": turn} for c in removed)
        self.constraints = [c for c in self.constraints if c not in removed]
        self.constraints.append(Constraint(key, value, negative, turn))

    def clear(self, turn):
        self.history.extend(
            {**asdict(c), "replaced_at": turn} for c in self.constraints
        )
        self.constraints.clear()


def parse(text, state, converter, turn, deadline):
    """Apply supported actions to a copy; callers publish only successful parses."""
    query = text.casefold().replace("’", "'").strip()
    state.event = "disclosure"
    browsing = bool(
        re.search(
            r"\b(brows(?:e|ing)|explor(?:e|ing)|still deciding|look around|not ready to buy|just looking)\b",
            query,
        )
    )
    buying = bool(
        re.search(
            r"\b(shopping intent to buying|ready to (?:buy|order)|buy now|purchase now|let's buy|i want to buy|i'll take)\b",
            query,
        )
    )
    if re.search(r"\b(not ready to buy|don't want to buy|do not want to buy)\b", query):
        buying = False
    if buying:
        state.mode, state.event = "buying", "mode_change"
    elif browsing:
        state.mode, state.event = "browsing", "mode_change"
    if re.search(
        r"\b(nothing else|nothing (?:more|else) to add|no further requirements|no extra requirement|anything works|no additional preference|no more preferences)\b",
        query,
    ):
        state.event = "missing"
        return state
    if re.search(
        r"\b(flexible about|you can decide|please choose|up to you|use your judgment)\b",
        query,
    ):
        state.event = "boundary"
        return state
    correction = bool(
        re.search(
            r"\b(actually|instead|rather|switch|change|make it|replace|forget|scratch|ignore|no longer)\b",
            query,
        )
    )
    # Full category phrases come only from the active catalog. Negated old
    # categories are excluded before selecting the new category.
    categories = [
        c
        for c in converter.categories
        if re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", query)
    ]
    categories = [c for c in categories if not any(c != other and c in other for other in categories)]
    categories.sort(key=lambda c: (query.rfind(c), len(c)))
    categories = [
        c
        for c in categories
        if not re.search(
            r"(?:not|forget|scratch|instead of|no longer want)\s+(?:the\s+)?$",
            query[: query.rfind(c)],
        )
    ]
    category = categories[-1] if categories else ""
    matcher = getattr(converter, "matcher", None)
    if not category and matcher and (not state.category or correction):
        opening = re.search(
            r"(?:looking for|need|find|show me(?: some)?|switch to|want)\s+([^.;!?]+)",
            query,
        )
        if opening:
            phrase = re.split(r"\b(?:with|that|but)\b", opening[1])[0].strip()
            category = matcher.match(phrase, converter.categories, deadline) or ""
    if category and state.category and category != state.category:
        state.clear(turn)
        state.event = "category_change"
    if category:
        state.category = category
    if not state.category:
        raise ValueError("Uncertain category; please name the product type")
    if re.search(
        r"\b(?:forget|ignore|clear) (?:all |my )?(?:earlier |previous )?(?:preferences|requirements|constraints)\b",
        query,
    ):
        state.clear(turn)
        state.event = "reset_preferences"

    if correction and re.search(
        r"(?:previous|earlier) preference|what i said earlier", query
    ):
        removed = [c for c in state.constraints if c.turn == 1]
        state.history.extend({**asdict(c), "replaced_at": turn} for c in removed)
        state.constraints = [c for c in state.constraints if c not in removed]
        state.event = "override"
    # Match each clause separately: whole-turn similarity mixes category, mode
    # and attribute semantics. Operators remain rules, never vector arithmetic.
    found = 0
    masked = query
    literal_values, _ = converter.evidence(query)
    for i, value in enumerate(literal_values):
        if value not in categories:
            masked = masked.replace(value, f"__evidence_{i}__")
    for clause in re.split(r"[.;!?]|\bbut\b|,|\band\b", masked):
        operator_clause = clause
        for i, value in enumerate(literal_values):
            clause = clause.replace(f"__evidence_{i}__", value)
        clause = clause.strip()
        if not clause:
            continue
        negative = bool(
            re.search(
                r"\b(not|no|without|avoid|exclude|don't want|do not want|no longer)\b",
                operator_clause,
            )
        )
        # Mode negation and undecided fillers are not product exclusions.
        if re.search(
            r"not ready|not sure|no particular|no preference|undecided|no idea|just looking",
            clause,
        ):
            continue
        evidence_clause = clause
        for c in sorted(categories, key=len, reverse=True):
            evidence_clause = evidence_clause.replace(c, "")
        values, shortlist = converter.evidence(evidence_clause)
        # Bare function words can exist as catalog evidence values; never
        # accept them as a preference on their own.
        values = [
            v
            for v in values
            if v
            not in ("for", "and", "the", "with", "from", "also", "some", "yet", "of")
        ]
        if not values and re.fullmatch(
            r"(?:just\s+|also\s+)?"
            r"(?:can you find|i need|i am browsing|(?:i'm\s+|i am\s+)?brows\w+|looking around|show me some|i'm looking for|i want|i am looking for|please find|forget|switch to)?"
            r"\s*(?:for|some|around)?\s*",
            evidence_clause.strip(),
        ):
            continue
        if not values and matcher:
            phrase = re.sub(
                r"^(?:(?:i )?(?:would |really )?(?:prefer|want|need)|(?:the important part|my preference) is|it (?:needs to|must) be|make it|keep|actually|not|without|avoid|instead)\s*:?\s*",
                "",
                evidence_clause,
            ).strip()
            if (
                phrase
                and phrase != clause
                or re.search(r"prefer|needs to|must be|make it|without|avoid", clause)
            ):
                active = set(converter.category_values.get(state.category, ()))
                choices = [v for v in shortlist if v in active]
                choices += sorted(
                    v for v in active if len(v.split()) <= 5 and v not in choices
                )
                value = (
                    matcher.match(phrase, choices[:256], deadline) if phrase else None
                )
                if value:
                    values = [value]
                elif phrase and not any(
                    word in clause for word in ("brows", "buy", "deciding")
                ):
                    raise ValueError(
                        "Uncertain evidence; please clarify the preference"
                    )
        if not values and re.search(
            r"\b(prefer|preference|must|without|avoid|exclude|make it)\b", clause
        ):
            raise ValueError("Uncertain evidence; please clarify the preference")
        for value in values:
            # 'red instead of blue' has opposite polarities within one clause.
            value_negative = negative
            if "instead of" in clause:
                value_negative = clause.find(value) > clause.find("instead of")
            state.put(value, value_negative, turn, replace=correction)
            found += 1
    if correction and found and state.event == "disclosure":
        state.event = "correction"
    if not found and not category and state.event == "disclosure":
        raise ValueError("No supported preference or shopping action found")
    return state


def accepts(product, state, evidence=()):
    from evaluator.local_evaluator import coarse_category

    if not product or not product.get("available", True):
        return False
    if normalized(coarse_category(product.get("categories", []))) != normalized(
        state.category
    ):
        return False
    body = (
        " "
        + normalized(
            json.dumps(
                {
                    k: product.get(k)
                    for k in (
                        "title",
                        "features",
                        "description",
                        "details",
                        "store",
                        "price",
                    )
                }
            )
        )
        + " "
    )
    for c in state.constraints:
        # Field labels may be synthesized by the evaluator; check their value.
        value = c.value.split(":", 1)[-1].strip()
        present = c.value in evidence or (" " + normalized(value) + " ") in body
        if present == c.negative:
            return False
    return True
