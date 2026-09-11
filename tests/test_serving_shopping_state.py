"""Behavioral regression fixtures, not a held-out natural-language benchmark."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from search_runtime.catalog import Catalog
from search_runtime.common import write_jsonl
from search_runtime.factory import create
from search_runtime.intent import PhraseMatcher


def product(asin, color, category="Shirts"):
    return {
        "parent_asin": asin,
        "title": f"{color} cotton {category}",
        "categories": ["Clothing", category],
        "features": [color, "cotton"],
        "details": {},
        "price": 20,
    }


class ShoppingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = root / "products.jsonl"
        write_jsonl(
            source,
            [
                product("R", "red"),
                product("B", "blue"),
                product("H", "black", "Headphones"),
            ],
        )
        self.store = Catalog(root / "store", source)
        self.agent = create(self.store, "rules")
        self.agent.reset("s", {})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def say(self, text, turn):
        result = self.agent.respond("s", text, turn, 10)
        return [r["parent_asin"] for r in result["recommendations"]]

    def test_partial_correction_retains_material(self):
        self.assertEqual(self.say("I need shirts. I prefer red and cotton.", 1), ["R"])
        self.assertEqual(self.say("Keep cotton, make it blue instead.", 2), ["B"])
        state = self.agent.states["s"]["shopping"]
        self.assertEqual({c.value for c in state.constraints}, {"cotton", "blue"})
        self.assertTrue(any(c["value"] == "red" for c in state.history))

    def test_browsing_buying_and_back(self):
        self.say("Show me shirts, I'm just looking around.", 1)
        self.assertEqual(self.agent.states["s"]["shopping"].mode, "browsing")
        self.say("I'm done browsing, I'm ready to buy now. I prefer blue.", 2)
        self.assertEqual(self.agent.states["s"]["shopping"].mode, "buying")
        self.say("Actually, I'm not ready to buy, just browsing.", 3)
        self.assertEqual(self.agent.states["s"]["shopping"].mode, "browsing")
        self.assertEqual(
            {c.value for c in self.agent.states["s"]["shopping"].constraints}, {"blue"}
        )

    def test_category_switch_clears_incompatible_constraints(self):
        self.say("I need shirts. I prefer blue.", 1)
        self.assertEqual(
            self.say("Forget shirts. I want headphones instead.", 2), ["H"]
        )
        self.assertEqual(self.agent.states["s"]["shopping"].constraints, [])

    def test_negation_excludes_products(self):
        self.assertEqual(self.say("I need shirts, not red.", 1), ["B"])
        self.assertTrue(self.agent.states["s"]["shopping"].constraints[0].negative)

    def test_protocol_preferences_survive_natural_correction(self):
        self.say("I'm looking for shirts. A key requirement is: cotton.", 1)
        self.assertEqual(self.agent.trace["s"]["route"], "protocol")
        self.assertEqual(self.say("Actually make it blue.", 2), ["B"])
        self.assertEqual(
            {c.value for c in self.agent.states["s"]["shopping"].constraints},
            {"blue", "cotton"},
        )

    def test_false_override_and_session_isolation(self):
        self.say("I need shirts. I prefer cotton.", 1)
        self.say("I prefer blue, actually.", 2)
        self.assertIn(
            "cotton", {c.value for c in self.agent.states["s"]["shopping"].constraints}
        )
        self.agent.reset("other", {})
        self.assertEqual(self.agent.states["other"]["shopping"].constraints, [])

    def test_deleted_evidence_and_reintroduction(self):
        self.say("I need shirts. I prefer blue.", 1)
        self.store.apply([{"parent_asin": "B", "revision": 1, "operation": "delete"}])
        self.assertEqual(self.say("I'm ready to buy now.", 2), [])
        self.assertNotIn("blue", self.agent.converter.values)
        self.store.apply(
            [
                {
                    "parent_asin": "B",
                    "revision": 2,
                    "operation": "upsert",
                    "product": product("B", "blue"),
                }
            ]
        )
        self.assertEqual(self.say("I'm ready to buy now.", 3), ["B"])

    def test_minilm_protocol_never_initializes_encoder(self):
        agent = create(self.store, "minilm")
        agent.reset("p", {})
        with patch(
            "search_runtime.models.Embeddings",
            side_effect=AssertionError("encoder must be bypassed"),
        ):
            agent.respond(
                "p", "I'm looking for shirts. A key requirement is: cotton.", 1, 10
            )
        self.assertEqual(agent.model_calls, 0)

    def test_removed_routes_rejected(self):
        for mode in ("qwen", "api"):
            with self.assertRaises(ValueError):
                create(self.store, mode)

    def test_category_request_is_not_an_attribute(self):
        result = self.say("Can you find shirts? I prefer cotton.", 1)
        self.assertTrue(result)
        self.assertEqual(self.agent.trace["s"]["route"], "translated-protocol")

    def test_catalog_budget_evidence_is_supported(self):
        result = self.say("I need shirts. My preference is budget around $20.", 1)
        self.assertTrue(result)
        self.assertNotEqual(self.agent.trace["s"]["route"], "raw-lexical-fallback")

    def test_no_more_preferences_preserves_state(self):
        self.say("I need shirts. I prefer cotton.", 1)
        self.say("Nothing else to add about other.", 2)
        self.assertEqual(self.agent.states["s"]["shopping"].event, "missing")
        self.assertEqual([c.value for c in self.agent.states["s"]["shopping"].constraints], ["cotton"])

    def test_semantic_value_flows_into_same_retriever(self):
        class Encoder:
            def encode(self, texts):
                mapping = {
                    "ocean coloured": [1, 0, 0],
                    "blue": [1, 0, 0],
                    "red": [0, 1, 0],
                    "cotton": [0, 0, 1],
                }
                return np.array([mapping[t] for t in texts], dtype="float32")

        agent = create(self.store, "minilm")
        agent.converter.matcher.encoder = Encoder()
        agent.reset("semantic", {})
        result = agent.respond(
            "semantic", "I need shirts. I prefer ocean coloured.", 1, 10
        )
        self.assertEqual(result["recommendations"], [{"parent_asin": "B"}])
        self.assertEqual(
            agent.trace["semantic"]["state"]["constraints"][0]["value"], "blue"
        )
        self.assertIn(
            "blue", agent.trace["semantic"]["canonical_text"]
        )

    def test_uncertain_turn_does_not_partially_mutate_preferences(self):
        self.say("I need shirts. I prefer red.", 1)
        self.say("Make it blue. It must levitate.", 2)
        self.assertEqual(self.agent.trace["s"]["route"], "raw-lexical-fallback")
        self.assertEqual(
            [c.value for c in self.agent.states["s"]["shopping"].constraints], ["red"]
        )


class VectorTests(unittest.TestCase):
    def test_cache_threshold_margin_numbers_and_active_candidates(self):
        class Encoder:
            def encode(self, texts):
                return np.array(
                    [[0.0, 1.0] if t == "wool" else [1.0, 0.0] for t in texts],
                    dtype="float32",
                )

        with tempfile.TemporaryDirectory() as root:
            mapper = PhraseMatcher(Path(root), Encoder())
            deadline = time.perf_counter() + 10
            self.assertEqual(
                mapper.match("soft plant fibre", ["cotton", "wool"], deadline), "cotton"
            )
            count = mapper.encoded
            self.assertEqual(
                mapper.match("soft plant fibre", ["cotton", "wool"], deadline), "cotton"
            )
            self.assertEqual(mapper.encoded, count)
            self.assertIsNone(mapper.match("soft plant fibre", ["wool"], deadline))
            self.assertIsNone(
                mapper.match("soft plant fibre", ["cotton", "linen"], deadline)
            )
            self.assertIsNone(mapper.match("100% cotton", ["80% cotton"], deadline))
            self.assertEqual(
                mapper.match("soft plant fibre", ["cotton"], deadline), "cotton"
            )
            self.assertEqual(mapper.encoded, count + 1)


if __name__ == "__main__":
    unittest.main()
