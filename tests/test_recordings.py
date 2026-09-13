"""Validate committed demo data without starting the API or loading the catalog."""
import json
import unittest
from pathlib import Path

from api.models import TurnResponse


class RecordedDemoTests(unittest.TestCase):
    def test_recordings_are_complete_real_traces(self):
        root = Path(__file__).resolve().parents[1] / "web/public/recordings"
        manifest = json.loads((root / "manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertGreaterEqual(len(manifest["examples"]), 10)
        self.assertEqual(manifest["provenance"]["catalog_size"], 50000)
        self.assertRegex(manifest["provenance"]["source_commit"], r"^[a-f0-9]{40}$")
        self.assertRegex(manifest["provenance"]["catalog_sha256"], r"^[a-f0-9]{64}$")
        seen = set()
        for example in manifest["examples"]:
            self.assertNotIn(example["id"], seen)
            seen.add(example["id"])
            for mode in ("structured", "natural"):
                with self.subTest(example=example["id"], mode=mode):
                    spec = example["recordings"][mode]
                    self.assertEqual(Path(spec["file"]).name, spec["file"])
                    recording = json.loads((root / spec["file"]).read_text())
                    self.assertEqual(recording["example_id"], example["id"])
                    self.assertEqual(recording["mode"], mode)
                    self.assertEqual(len(recording["turns"]), len(example["turns"]))
                    decisions = []
                    for number, turn in enumerate(recording["turns"], 1):
                        response = TurnResponse(**turn["response"])
                        self.assertEqual(turn["input"], example["turns"][number-1][mode])
                        self.assertEqual(response.turn, number)
                        self.assertTrue(response.trace)
                        self.assertLessEqual(len(response.recommendations), 10)
                        self.assertFalse(response.trace["extension"].get("fallback_reason"))
                        self.assertEqual([p.parent_asin for p in response.recommendations], response.trace["selection"]["selected"])
                        self.assertEqual(bool(response.trace.get("semantic")), mode == "natural")
                        decisions.append(response.trace["selection"]["decision"])
                    self.assertEqual(response.recommendations[0].parent_asin, example["target_asin"])
                    if example["scenario"] == "rotation":
                        self.assertIn("rotation", decisions)
