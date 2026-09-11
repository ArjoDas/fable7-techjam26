"""Serving-only normalization: no samples, targets, paraphrase banks or hidden cards."""

import json
import re
import time
from collections import defaultdict, Counter
from extension.events import Event, canonical


def norm(text):
    return re.sub(r"\s+", " ", text).strip(" .;,").casefold()


def tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


class Converter:
    def __init__(self, store, mode="rules", vectors=None, threshold=0.65):
        self.store = store
        if mode not in ("rules", "minilm"):
            raise ValueError("Supported routes are rules and minilm")
        self.mode = mode
        self.matcher = None
        if mode == "minilm":
            from extension.intent import PhraseMatcher

            self.matcher = PhraseMatcher(store.directory, threshold=threshold)
        self.vectors = vectors
        self.threshold = threshold
        self.version = -1
        self.refresh()

    def refresh(self):
        if self.version == self.store.version:
            return
        from evaluator.local_evaluator import intent_card, coarse_category
        from starter.agent import _normalized_value

        if self.version < 0:
            self.values = set()
            self.categories = set()
            self.postings = defaultdict(set)
            self.token_values = defaultdict(set)
            self.value_counts = Counter()
            self.category_counts = Counter()
            self.category_values = defaultdict(Counter)
            self.length_counts = Counter()
            self.product_evidence = {}
            self.surface_values = defaultdict(set)
            self.surfaces = {}
            self.processed_products = 0
            changed = set(self.store.products)
        else:
            changed = set()
            for (payload,) in self.store.db.execute(
                "SELECT events FROM events WHERE version>?", (self.version,)
            ):
                changed.update(json.loads(payload)["changed"])
        # Catalog-wide evidence preprocessing, never the evaluator's target card.
        # Preserve punctuation/units that the positional index intentionally strips.
        touched = set()
        for asin in changed:
            previous = self.product_evidence.pop(asin, None)
            if previous:
                category, values = previous
                self.category_counts[category] -= 1
                if not self.category_counts[category]:
                    self.categories.discard(category)
                for value in values:
                    self.category_values[category][value] -= 1
                    if not self.category_values[category][value]:
                        del self.category_values[category][value]
                    self.value_counts[value] -= 1
                    if self.value_counts[value]:
                        continue
                    self.values.discard(value)
                    sequence = tuple(re.findall(r"\w+", value))
                    self.token_values[sequence].discard(value)
                    self.length_counts[len(sequence)] -= 1
                    for word in tokens(value):
                        self.postings[word].discard(value)
                    normalized = _normalized_value(value)
                    self.surface_values[normalized].discard(value)
                    touched.add(normalized)
            product = self.store.products.get(asin)
            if not product or not product.get("available", True):
                continue
            card = intent_card(product)
            category = norm(coarse_category(product.get("categories", [])))
            values = set()
            for value in card["hard_constraints"] + card["soft_preferences"]:
                values.add(norm(value))
                values.update(
                    norm(fragment) for fragment in value.split(";") if norm(fragment)
                )
            self.product_evidence[asin] = (category, values)
            self.categories.add(category)
            self.category_counts[category] += 1
            for value in values:
                self.category_values[category][value] += 1
                self.value_counts[value] += 1
                if self.value_counts[value] > 1:
                    continue
                self.values.add(value)
                sequence = tuple(re.findall(r"\w+", value))
                self.token_values[sequence].add(value)
                self.length_counts[len(sequence)] += 1
                for word in tokens(value):
                    self.postings[word].add(value)
                normalized = _normalized_value(value)
                self.surface_values[normalized].add(value)
                touched.add(normalized)
        for normalized in touched:
            if self.surface_values[normalized]:
                self.surfaces[normalized] = max(self.surface_values[normalized])
            else:
                self.surfaces.pop(normalized, None)
        self.max_words = max(
            (n for n, count in self.length_counts.items() if count), default=0
        )
        self.processed_products += len(changed)
        self.version = self.store.version

    def evidence(self, text):
        query = norm(text)
        words = re.findall(r"\w+", query)
        matches = set()
        for start in range(len(words)):
            for end in range(start + 1, min(len(words), start + self.max_words) + 1):
                matches.update(self.token_values.get(tuple(words[start:end]), ()))
        exact = sorted(
            (v for v in matches if v in query), key=lambda v: (query.index(v), -len(v))
        )
        selected = []
        last = -1
        for value in exact:
            position = query.index(value)
            if position >= last:
                selected.append(value)
                last = position + len(value)
        if self.mode == "rules":
            return selected, []
        possible = set()
        for word in sorted(tokens(query), key=lambda w: len(self.postings.get(w, ()))):
            if len(self.postings.get(word, ())) > 5000:
                continue
            possible.update(self.postings.get(word, ()))
            if len(possible) > 5000:
                break
        shortlist = sorted(
            possible,
            key=lambda v: (
                -len(tokens(v) & tokens(query)) / max(1, len(tokens(v))),
                -len(v),
                v,
            ),
        )[:50]
        return selected, shortlist


class TranslatedAgent:
    def __init__(self, store, mode="rules", vectors=None, threshold=0.65):
        from extension.protocol import ProtocolGuard

        self.store = store
        self.converter = Converter(store, mode, vectors, threshold)
        self.states = {}
        self.trace = {}
        self.model_calls = 0
        self.vectors = vectors
        self.guard = ProtocolGuard(catalog=store)

    def reset(self, sid, profile):
        self.guard.reset(sid, profile)
        from extension.intent import ShoppingState

        self.states[sid] = {
            "started": False,
            "asked": None,
            "shopping": ShoppingState(),
        }

    def close(self, sid):
        self.guard.close(sid)
        self.states.pop(sid, None)
        self.trace.pop(sid, None)

    def sync_catalog(self):
        self.store.sync()
        if self.guard._version != self.store.version:
            changed = set()
            for (payload,) in self.store.db.execute(
                "SELECT events FROM events WHERE version>?", (self.guard._version,)
            ):
                changed.update(json.loads(payload)["changed"])
            self.guard.base = self.store.agent
            self.guard._prepare(changed)
        self.converter.refresh()
        if self.vectors is not None:
            self.vectors.sync(self.store)

    def respond(self, sid, text, turn, top_k):
        # Synchronize in-process publication with the complete read operation.
        with self.store.lock:
            return self._respond(sid, text, turn, top_k)

    def _respond(self, sid, text, turn, top_k):
        from dataclasses import asdict
        import copy
        from extension.events import decode
        from extension.intent import parse, accepts
        from starter.cp5_dialogue import normalize_protocol_text

        began = time.perf_counter()
        self.sync_catalog()
        event, error = None, None
        state = self.states[sid]
        guard_state = copy.deepcopy(self.guard.states[sid])
        bypass = self.guard._protocol(guard_state, normalize_protocol_text(text), turn)
        matcher = self.converter.matcher
        if matcher:
            matcher.last = None
        calls_before = matcher.calls if matcher else 0
        message = text
        if bypass:
            # Exact public behavior; never initialize or call the encoder here.
            result = self.store.agent.respond(sid, text, turn, top_k)
            event = decode(text)
            shopping = state["shopping"]
            if event.category:
                if shopping.category and norm(event.category) != shopping.category:
                    shopping.clear(turn)
                shopping.category = norm(event.category)
            if event.kind == "browse":
                shopping.mode = "browsing"
            if event.kind == "override":
                # Main's official override replaces the opening preference only.
                prior = [c for c in shopping.constraints if c.turn == 1]
                shopping.history.extend(
                    {**asdict(c), "replaced_at": turn} for c in prior
                )
                shopping.constraints = [
                    c for c in shopping.constraints if c not in prior
                ]
            for value in event.values:
                shopping.put(norm(value), False, turn)
            shopping.event = event.kind
            route = "protocol"
        else:
            shopping = copy.deepcopy(state["shopping"])
            try:
                deadline = min(
                    began + 1.2, getattr(self, "request_deadline", began + 2) - 0.7
                )
                shopping = parse(text, shopping, self.converter, turn, deadline)
                state["shopping"] = shopping
                route = "minilm-rules" if matcher else "rules-state"
            except Exception as exc:
                error = type(exc).__name__ + ": " + str(exc)
                shopping = state["shopping"]
                route = "raw-lexical-fallback"
            translated = None
            current = [c for c in shopping.constraints if c.turn == turn]
            if not error and not any(c.negative for c in current):
                values = tuple(c.value for c in current)
                if turn == 1 and shopping.category:
                    if shopping.mode == "browsing" and not values:
                        translated = Event("browse", shopping.category)
                    elif len(values) == 1:
                        kind = (
                            "opening_old"
                            if re.search(r"\b(prefer|preference)\b", text, re.I)
                            else "opening"
                        )
                        translated = Event(kind, shopping.category, values)
                elif shopping.event in ("missing", "boundary"):
                    translated = Event(
                        shopping.event, attribute=state.get("asked") or "other"
                    )
                elif shopping.event == "override" and len(values) == 1:
                    translated = Event("override", values=values)
                elif shopping.event == "disclosure" and 1 <= len(values) <= 2:
                    translated = Event("disclosure", values=values)
            candidate_guard = copy.deepcopy(self.guard.states[sid])
            if translated and self.guard._protocol(
                candidate_guard, normalize_protocol_text(canonical(translated)), turn
            ):
                event = translated
                message = canonical(event)
                result = self.store.agent.respond(sid, message, turn, top_k)
                result["recommendations"] = [r for r in result["recommendations"] if accepts(self.store.products.get(r["parent_asin"]), shopping, self.converter.product_evidence.get(r["parent_asin"], (None, set()))[1])]
                guard_state = candidate_guard
                route = "translated-protocol"
            else:
                # Explicit state is rendered into the same constrained evidence
                # sentences, but never fabricates an official dialogue prefix.
                base = self.store.agent._sessions[sid]
                base["protocol_compatible"] = False
                base["messages"] = (
                    [canonical(Event("browse", shopping.category))]
                    if shopping.category
                    else []
                )
                positives = [c.value for c in shopping.constraints if not c.negative]
                base["messages"].extend(
                    canonical(Event("disclosure", values=(v,))) for v in positives
                )
                if error:
                    base["messages"].append(text)
                if shopping.event in (
                    "correction",
                    "category_change",
                    "reset_preferences",
                ):
                    base["shown"] = set()
                    base["last_signature"] = None
                base.update(
                    category_query=shopping.category,
                    exploratory=shopping.mode == "browsing",
                    override_seen=shopping.event in ("correction", "category_change"),
                )
                message = " ".join(base["messages"])
                result = self.store.agent.respond(
                    sid,
                    canonical(Event("missing", attribute="other")),
                    max(2, turn),
                    top_k,
                )
                ranked = list(
                    dict.fromkeys(
                        [r["parent_asin"] for r in result["recommendations"]]
                        + base.get("last_ranking", [])
                    )
                )
                if shopping.event in ("missing", "boundary"):
                    message = canonical(Event(shopping.event, attribute="other"))
                valid = [
                    a
                    for a in ranked
                    if (
                        accepts(
                            self.store.products.get(a),
                            shopping,
                            self.converter.product_evidence.get(a, (None, set()))[1],
                        )
                        if shopping.category
                        else self.store.products.get(a, {}).get("available", True)
                    )
                ]
                result["recommendations"] = [{"parent_asin": a} for a in valid[:top_k]]
                if error:
                    result["message"] = (
                        "Could you clarify the product type or preference? Here are any matches to the preferences understood so far."
                    )
                elif shopping.mode == "browsing":
                    result["message"] = (
                        "Here are options to explore. Is there a feature you would like to narrow down?"
                    )
                elif not valid:
                    result["message"] = (
                        "No available matches satisfy the preferences understood so far. Which preference could we change?"
                    )
                guard_state["protocol"] = False
        calls = (matcher.calls - calls_before) if matcher else 0
        self.model_calls += calls
        state.update(started=True, asked=result.get("ask_attribute"))
        guard_state.update(turn=turn, ask=result.get("ask_attribute"))
        self.guard.states[sid] = guard_state
        # Direct users get the same availability protection as HTTP workers.
        result["recommendations"] = [
            r
            for r in result["recommendations"]
            if self.store.products.get(r["parent_asin"], {}).get("available", True)
            and r["parent_asin"] in self.store.products
        ]
        self.trace[sid] = {
            "route": route,
            "version": self.store.version,
            "event": asdict(event) if event else None,
            "state": asdict(state["shopping"]),
            "canonical_text": message,
            "fallback_reason": error,
            "model_calls": calls,
            "usage": {},
            "elapsed_ms": (time.perf_counter() - began) * 1000,
            "mapping": matcher.last if matcher else None,
            "candidate_ids": self.store.agent._sessions[sid].get("last_candidates", [])[
                :100
            ],
        }
        return result
