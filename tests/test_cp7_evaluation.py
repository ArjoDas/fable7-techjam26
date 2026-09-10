import unittest

from scripts.evaluate_cp7 import compare


def outcome(identifier, turn, rr):
    return {"sample_id": identifier, "hit": turn is not None,
            "first_hit_turn": turn, "reciprocal_rank": rr}


class PairedGateTest(unittest.TestCase):
    def test_aggregate_improvement_cannot_hide_one_regression(self):
        before = {"sessions": [outcome("a", 2, 1), outcome("b", 10, .1)]}
        after = {"sessions": [outcome("a", 1, .5), outcome("b", 1, 1)]}
        self.assertEqual(compare(before, after), {
            "regressions": 1, "improved_sessions": 1, "turns_saved": 10,
        })

    def test_misses_are_turn_eleven(self):
        before = {"sessions": [outcome("a", None, 0)]}
        after = {"sessions": [outcome("a", 10, .1)]}
        self.assertEqual(compare(before, after), {
            "regressions": 0, "improved_sessions": 1, "turns_saved": 1,
        })

    def test_missing_and_duplicate_identities_fail(self):
        before = {"sessions": [outcome("a", 1, 1)]}
        for after in ({"sessions": []}, {"sessions": before["sessions"]*2}):
            with self.assertRaises(ValueError):
                compare(before, after)


if __name__ == "__main__":
    unittest.main()
