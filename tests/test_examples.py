"""The bundled demo must retain a varied set of identifiable targets."""
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from api.examples import build_examples
from api.products import ProductCatalog
from starter.cp5_dialogue import DialogueCardIndex


class CuratedExamplesTests(unittest.TestCase):
    def test_bundled_examples_are_diverse_and_have_unique_final_evidence(self):
        path = Path(__file__).resolve().parents[1] / "data/catalog.jsonl"
        if not path.exists():
            self.skipTest("Bundled catalog is not installed")
        index = DialogueCardIndex(path)
        products = ProductCatalog(path)
        agent = SimpleNamespace(_dialogue_index=index, _popularity={})
        examples = build_examples(agent, products)
        self.assertGreaterEqual(len(examples), 10)
        self.assertEqual(len({e["target_asin"] for e in examples}), len(examples))
        self.assertEqual(Counter(e["scenario"] for e in examples),
                         {"buying": 4, "browsing": 4, "rotation": 2, "override": 2})
        for example in examples:
            with self.subTest(example=example["label"]):
                card = index.cards[example["target_asin"]]
                self.assertGreater(len(index.prefixes[(card.category, card.sequence[0])]), 1)
                self.assertEqual(index.prefixes[(card.category, *card.sequence[:2])],
                                 [example["target_asin"]])
                self.assertNotRegex(example["category"], r"underwear|bikini|lingerie")
                self.assertTrue(all(t["structured"] and t["natural"] for t in example["turns"]))
