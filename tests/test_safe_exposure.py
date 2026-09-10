from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent
from starter.cp5_dialogue import DialogueCardIndex, candidate_sequence
from starter.safe_exposure import ExposureHistory, protect_output


class ExposureTest(unittest.TestCase):
    def test_eligibility_boundary_and_override(self):
        h = ExposureHistory()
        h.observe("I'm looking for Men Shirts. Imported", 1, True)
        h.pending = ("TARGET",)
        h.observe("For that, what matters is: cotton; color: black.", 2, True)
        self.assertFalse(h.active)
        self.assertEqual(h.refuted, set())
        h.observe("Actually, ignore my earlier preference. What I need is: cotton.", 3, True)
        self.assertTrue(h.active)
        self.assertEqual(h.refuted, set())
        h.pending = ("A",)
        h.observe("I don't have a preference for other; please use your judgment.", 4, True)
        self.assertEqual(h.refuted, {"A"})
        self.assertFalse(h.exhausted)
        h.pending = ("B",)
        h.observe("I don't have an additional preference for other.", 5, True)
        self.assertTrue(h.exhausted)
        self.assertEqual(h.refuted, {"A", "B"})

    def test_unsupported_or_skipped_turn_latches_off(self):
        for message, turn in (("I care about cotton.", 2),
                              ("For that, what matters is: cotton.", 3)):
            h = ExposureHistory()
            h.observe("I'm looking for Men Shirts, but I'm still exploring.", 1, True)
            h.pending = ("A",)
            h.observe(message, turn, True)
            h.observe("Actually, ignore my earlier preference. What I need is: cotton.", turn + 1, True)
            self.assertFalse(h.active)
            self.assertEqual(h.refuted, set())

    def test_only_refuted_singletons_are_replaced(self):
        h = ExposureHistory(eligible=True, refuted={"A"})
        kwargs = dict(history=h, turn=3, top_k=10, singleton=True,
                      batching=False, future_reference=set())
        self.assertEqual(protect_output(["A"], ["A", "B"], ["A", "C"], **kwargs), ["C"])
        self.assertEqual(protect_output(["B"], ["A", "B"], ["C"], **kwargs), ["B"])
        self.assertEqual(protect_output(["A", "B"], ["A", "B"], ["C"], **kwargs), ["A", "B"])
        self.assertEqual(protect_output(["A"], ["A"], [], **kwargs), ["A"])

    def test_batching_protects_future_hits_and_requires_exhaustion(self):
        h = ExposureHistory(eligible=True, exhausted=True, refuted={"A"})
        kwargs = dict(reference=["B"], ranked=["A", "B", "C"],
                      cohort=["A", "B", "C", "D"], history=h, turn=4, top_k=10,
                      singleton=False, batching=True, future_reference={"B", "C"})
        self.assertEqual(protect_output(**kwargs), ["B", "D"])
        h.exhausted = False
        self.assertEqual(protect_output(**kwargs), ["B"])

    def test_final_turn_preserves_reference_order_and_reaches_past_80(self):
        cohort = [f"A{i:03}" for i in range(120)]
        h = ExposureHistory(eligible=True, refuted=set(cohort[:90]))
        out = protect_output(["A091", "A005", "A090"], cohort[:80], cohort, h, 10, 10,
                             singleton=True, batching=False, future_reference=set())
        self.assertEqual(out[:2], ["A091", "A090"])
        self.assertEqual(len(out), 10)
        self.assertEqual(len(set(out)), 10)
        self.assertFalse(set(out) & h.refuted)


class IntegratedExposureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "catalog.jsonl"
        rows = [{"parent_asin": f"A{i:03}", "title": "Black cotton shirt",
                 "categories": ["Men", "Shirts"], "rating_number": 200-i,
                 "features": ["Imported", "Machine Wash"], "details": {}}
                for i in range(120)]
        self.path.write_text("".join(json.dumps(r)+"\n" for r in rows))
        self.agents = []

    def tearDown(self):
        for a in self.agents:
            a.connection.close()
        self.temp.cleanup()

    def agent(self, single=True, batch=False):
        a = Agent(self.path, use_safe_refutation=single, use_safe_exhaustion=batch)
        a.reset("s", {})
        self.agents.append(a)
        return a

    def test_reference_history_stays_independent_and_reset_is_clean(self):
        a, baseline = self.agent(), self.agent(False)
        messages = ["I'm looking for Men Shirts. A key requirement is: cotton.",
                    "For that, what matters is: color: black; Imported.",
                    "For that, what matters is: Machine Wash."]
        for turn, msg in enumerate(messages, 1):
            actual = a.respond("s", msg, turn, 10)
            ref = baseline.respond("s", msg, turn, 10)
            self.assertEqual(a._sessions["s"]["shown"], baseline._sessions["s"]["shown"])
            self.assertEqual(a._sessions["s"]["last_reference_output"],
                             [r["parent_asin"] for r in ref["recommendations"]])
        self.assertEqual(actual["recommendations"][0]["parent_asin"], "A002")
        self.assertEqual(a._sessions["s"]["shown"], {"A000"})
        a.reset("other", {})
        self.assertEqual(a._sessions["other"]["safe_exposure"].refuted, set())
        self.assertNotEqual(a._sessions["s"]["safe_exposure"].refuted, set())

    def test_exhausted_rollout_matches_real_reference_responses(self):
        a = self.agent(False)
        messages = ["I'm looking for Men Shirts. A key requirement is: cotton.",
                    "For that, what matters is: color: black; Imported.",
                    "For that, what matters is: Machine Wash.",
                    "I don't have an additional preference for other."]
        for turn, msg in enumerate(messages, 1):
            response = a.respond("s", msg, turn, 10)
        s = a._sessions["s"]
        current = [r["parent_asin"] for r in response["recommendations"]]
        shown_before = set(s["shown"])
        predicted = a._future_reference(s, s["last_ranking"], s["last_signature"],
                                       a._constraint_phrases(s["messages"]), 4, 10, current)
        self.assertEqual(shown_before, s["shown"])
        actual = set(current)
        for turn in range(5, 11):
            out = a.respond("s", messages[-1], turn, 10)
            actual.update(r["parent_asin"] for r in out["recommendations"])
        self.assertEqual(predicted, actual)

    def test_auxiliary_normalization_keeps_reference_lookup_unchanged(self):
        index = DialogueCardIndex(self.path)
        raw = ["cotton", "color: black", "color-black", "!!!", "Imported"]
        self.assertEqual(index.matching_prefix("Men Shirts", raw), ())
        self.assertEqual(len(index.matching_observed_prefix("Men Shirts", raw)), 120)
        self.assertEqual(index.matching_observed_prefix("Men Shirts", ["!!!"]), ())

    def test_every_target_preserves_cp6_and_singleton_outcomes_in_large_tie(self):
        # Every candidate shares the same disclosures, so one no-hit trajectory
        # gives the first exposure turn/rank for every possible target.
        policies = [self.agent(False), self.agent(True), self.agent(False, True),
                    self.agent(True, True)]
        outcomes = []
        for agent in policies:
            hits = {}
            for turn in range(1, 11):
                msg = {1: "I'm looking for Men Shirts. A key requirement is: cotton.",
                       2: "For that, what matters is: color: black; Imported.",
                       3: "For that, what matters is: Machine Wash."}.get(
                           turn, "I don't have an additional preference for other.")
                out = agent.respond("s", msg, turn, 10)
                for rank, item in enumerate(out["recommendations"], 1):
                    hits.setdefault(item["parent_asin"], (turn, 1/rank))
            outcomes.append(hits)
        for before, after in ((0, 1), (0, 2), (0, 3), (1, 3)):
            for asin, (turn, rr) in outcomes[before].items():
                new_turn, new_rr = outcomes[after].get(asin, (11, 0))
                self.assertLessEqual(new_turn, turn, (before, after, asin))
                self.assertGreaterEqual(new_rr, rr, (before, after, asin))
        self.assertGreater(len(outcomes[3]), len(outcomes[1]))
        self.assertGreater(len(outcomes[3]), 50)

    def test_semicolons_and_truncation(self):
        sequence = candidate_sequence({"title": "Cotton shirt", "features": ["Imported; Washable", "x"*200]})
        self.assertEqual(sequence, ("cotton", "imported", "washable", "x"*180))


if __name__ == "__main__":
    unittest.main()
