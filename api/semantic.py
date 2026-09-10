"""Map free natural-language text onto the catalog's known vocabulary.

The serving agent understands a small structured protocol (categories,
disclosed constraint values, intent switches).  This module bridges free text
to that protocol in two stages:

1. Lexical shortlist: token-overlap retrieval over the dialogue-card
   vocabulary (the exact values products can disclose).
2. Semantic rerank: a local MiniLM ONNX encoder scores the shortlist against
   the raw text by cosine similarity.  When the encoder is unavailable the
   lexical score alone is used.

Everything runs locally; no network calls.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")
BROWSE_RE = re.compile(
    r"\b(brows\w*|explor\w*|not sure|undecided|just looking|window shopping|no idea)\b"
)
OVERRIDE_RE = re.compile(
    r"\b(actually|instead|forget|scratch that|changed my mind|change of plans|nevermind|never mind)\b"
)
NO_PREFERENCE_RE = re.compile(
    r"\b(no (?:other |more |additional )?preference|anything works|whatever|nothing else|no further|that's all|thats all|don't care|dont care)\b"
)
BUY_SWITCH_RE = re.compile(r"\b(ready to buy|want to buy|buying now|purchase|decided)\b")
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "but", "by", "can", "do",
    "for", "from", "get", "have", "i", "in", "is", "it", "like", "looking",
    "me", "my", "need", "of", "on", "or", "please", "prefer", "really",
    "recommend", "show", "some", "something", "that", "the", "this", "to",
    "want", "with", "would", "you", "am", "im", "id", "ideally", "must",
    "should", "one", "them", "find", "buy", "shopping",
}
DEFAULT_MODEL_DIR = Path("data/releases/real-world-v1/models/minilm")


def _tokens(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]


class _Encoder:
    """Thin local MiniLM ONNX wrapper (mean pooling + L2 normalization)."""

    def __init__(self, model_dir: Path) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._np = np
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        model_path = model_dir / "onnx" / "model_quint8_avx2.onnx"
        if not model_path.exists():
            model_path = model_dir / "onnx" / "model.onnx"
        self.session = ort.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()
        self._cache: dict[str, Any] = {}

    def encode(self, texts: list[str]) -> Any:
        np = self._np
        missing = [text for text in texts if text not in self._cache]
        for offset in range(0, len(missing), 32):
            batch = missing[offset : offset + 32]
            encoded = self.tokenizer.encode_batch(batch)
            values = {
                "input_ids": np.array([item.ids for item in encoded], dtype=np.int64),
                "attention_mask": np.array(
                    [item.attention_mask for item in encoded], dtype=np.int64
                ),
                "token_type_ids": np.array(
                    [item.type_ids for item in encoded], dtype=np.int64
                ),
            }
            hidden = self.session.run(
                None, {inp.name: values[inp.name] for inp in self.session.get_inputs()}
            )[0]
            mask = values["attention_mask"][..., None]
            pooled = (hidden * mask).sum(1) / mask.sum(1).clip(1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(1e-9)
            for text, vector in zip(batch, pooled.astype("float32")):
                if len(self._cache) > 20000:
                    self._cache.clear()
                self._cache[text] = vector
        return np.stack([self._cache[text] for text in texts])


class SemanticMapper:
    """Translate free text into the closest known catalog keywords."""

    def __init__(
        self,
        agent: Any,
        model_dir: str | Path | None = None,
        value_threshold: float = 0.35,
        category_threshold: float = 0.30,
    ) -> None:
        self.value_threshold = value_threshold
        self.category_threshold = category_threshold
        self.categories: Counter[str] = Counter()
        self.values: Counter[str] = Counter()
        self.postings: dict[str, set[str]] = defaultdict(set)
        cards = getattr(getattr(agent, "_dialogue_index", None), "cards", None) or {}
        for card in cards.values():
            self.categories[card.category] += 1
            for value in card.sequence:
                self.values[value] += 1
        for value in self.values:
            for token in set(_tokens(value)):
                self.postings[token].add(value)
        self.encoder: _Encoder | None = None
        self.encoder_error: str | None = None
        try:
            self.encoder = _Encoder(Path(model_dir or DEFAULT_MODEL_DIR))
        except Exception as exc:  # onnxruntime/tokenizers missing or bad model
            self.encoder_error = f"{type(exc).__name__}: {exc}"

    # ── candidate scoring ──────────────────────────────────────────────

    def _category_candidates(self, text: str) -> list[dict[str, Any]]:
        lowered = " ".join(TOKEN_RE.findall(text.lower()))
        exact = [
            category
            for category in self.categories
            if category and re.search(r"(?<!\w)" + re.escape(category) + r"(?!\w)", lowered)
        ]
        if exact:
            exact.sort(key=len, reverse=True)
            return [
                {"category": category, "lexical": 1.0, "semantic": None, "score": 1.0}
                for category in exact[:5]
            ]
        query_tokens = set(_tokens(text))
        scored: list[tuple[float, str]] = []
        for category, count in self.categories.items():
            category_tokens = set(_tokens(category))
            if not category_tokens:
                continue
            overlap = len(category_tokens & query_tokens) / len(category_tokens)
            if overlap > 0.0:
                scored.append((overlap + min(count, 1000) / 1e6, category))
        scored.sort(reverse=True)
        shortlist = [category for _, category in scored[:12]]
        if not shortlist:
            return []
        semantic_scores = self._semantic_scores(text, shortlist)
        candidates = []
        for index, category in enumerate(shortlist):
            lexical = scored[index][0]
            semantic = semantic_scores[index] if semantic_scores is not None else None
            score = semantic if semantic is not None else lexical
            candidates.append(
                {
                    "category": category,
                    "lexical": round(lexical, 4),
                    "semantic": round(semantic, 4) if semantic is not None else None,
                    "score": round(score, 4),
                }
            )
        candidates.sort(key=lambda item: -item["score"])
        return candidates[:5]

    def _value_candidates(
        self, text: str, exclude_tokens: set[str]
    ) -> list[dict[str, Any]]:
        query_tokens = [
            token for token in _tokens(text) if token not in exclude_tokens
        ]
        query_set = set(query_tokens)
        if not query_set:
            return []
        overlap_counts: Counter[str] = Counter()
        for token in query_set:
            values = self.postings.get(token, ())
            if len(values) > 30000:
                continue
            for value in values:
                overlap_counts[value] += 1
        scored: list[tuple[float, str]] = []
        for value, overlap in overlap_counts.items():
            value_tokens = set(_tokens(value))
            if not value_tokens:
                continue
            precision = overlap / len(value_tokens)
            recall = overlap / len(query_set)
            lexical = 0.7 * precision + 0.3 * recall
            scored.append((lexical, value))
        scored.sort(key=lambda item: (-item[0], -self.values[item[1]], item[1]))
        shortlist = scored[:40]
        if not shortlist:
            return []
        semantic_scores = self._semantic_scores(text, [value for _, value in shortlist])
        candidates = []
        for index, (lexical, value) in enumerate(shortlist):
            semantic = semantic_scores[index] if semantic_scores is not None else None
            score = (
                0.45 * lexical + 0.55 * semantic if semantic is not None else lexical
            )
            candidates.append(
                {
                    "value": value,
                    "support": int(self.values[value]),
                    "lexical": round(lexical, 4),
                    "semantic": round(semantic, 4) if semantic is not None else None,
                    "score": round(score, 4),
                }
            )
        candidates.sort(key=lambda item: -item["score"])
        return candidates[:10]

    def _semantic_scores(self, query: str, candidates: list[str]) -> list[float] | None:
        if self.encoder is None or not candidates:
            return None
        try:
            vectors = self.encoder.encode([query, *candidates])
        except Exception as exc:
            self.encoder_error = f"{type(exc).__name__}: {exc}"
            self.encoder = None
            return None
        query_vector = vectors[0]
        return [float(query_vector @ vector) for vector in vectors[1:]]

    # ── canonical message composition ──────────────────────────────────

    def map(self, text: str, turn: int) -> dict[str, Any]:
        lowered = text.lower()
        browsing = bool(BROWSE_RE.search(lowered))
        override = turn > 1 and bool(OVERRIDE_RE.search(lowered))
        no_preference = turn > 1 and bool(NO_PREFERENCE_RE.search(lowered))
        buy_switch = turn > 1 and bool(BUY_SWITCH_RE.search(lowered))

        category_candidates = self._category_candidates(text) if turn == 1 else []
        chosen_category = None
        if category_candidates and category_candidates[0]["score"] >= self.category_threshold:
            chosen_category = str(category_candidates[0]["category"])

        exclude = set(_tokens(chosen_category)) if chosen_category else set()
        value_candidates = (
            [] if no_preference or buy_switch else self._value_candidates(text, exclude)
        )
        chosen_values = [
            str(candidate["value"])
            for candidate in value_candidates[:1]
            if candidate["score"] >= self.value_threshold
        ]

        canonical = self._compose(
            turn, chosen_category, chosen_values, browsing, override,
            no_preference, buy_switch,
        )
        return {
            "input": text,
            "browsing": browsing,
            "override": override,
            "no_preference": no_preference,
            "buy_switch": buy_switch,
            "encoder_used": self.encoder is not None,
            "encoder_error": self.encoder_error,
            "category_candidates": category_candidates,
            "chosen_category": chosen_category,
            "value_candidates": value_candidates,
            "chosen_values": chosen_values,
            "canonical_message": canonical,
        }

    @staticmethod
    def _compose(
        turn: int,
        category: str | None,
        values: list[str],
        browsing: bool,
        override: bool,
        no_preference: bool,
        buy_switch: bool,
    ) -> str | None:
        if no_preference:
            return "I don't have an additional preference for other."
        if buy_switch:
            return "I'm changing my shopping intent to buying."
        if override:
            if values:
                return (
                    "Actually, ignore my earlier preference. "
                    f"What I need is: {values[0]}."
                )
            return None
        if turn == 1:
            if not category:
                return None
            message = f"I'm looking for {category}"
            message += ", but I'm still exploring." if browsing else "."
            if values and not browsing:
                message += f" A key requirement is: {values[0]}."
            return message
        if values:
            return f"For that, what matters is: {'; '.join(values)}."
        return None
