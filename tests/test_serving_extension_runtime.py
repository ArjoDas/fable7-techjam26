import tempfile, unittest
from pathlib import Path
from search_runtime.common import write_jsonl
from search_runtime.translate import Converter
from search_runtime.intent import parse, ShoppingState
import time


def product(a, color):
    return {
        "parent_asin": a,
        "title": color + " cotton shirt",
        "categories": ["Clothing", "Shirts"],
        "features": [color, "cotton"],
        "details": {},
        "price": 20,
    }


class RuntimeTests(unittest.TestCase):
    def test_model_timeout_falls_back_and_direct_call_refreshes_catalog(self):
        from search_runtime.catalog import Catalog
        from search_runtime.translate import TranslatedAgent
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "catalog.jsonl"
            write_jsonl(path, [product("A", "red"), product("B", "blue")])
            store = Catalog(root / "store", path)
            try:
                agent = TranslatedAgent(store, mode="minilm")
                agent.reset("x", {})
                with patch(
                    "search_runtime.intent.PhraseMatcher.match",
                    side_effect=TimeoutError("deadline"),
                ):
                    result = agent.respond(
                        "x", "I need comfortable clothes for weekends", 1, 10
                    )
                self.assertEqual(agent.trace["x"]["route"], "raw-lexical-fallback")
                self.assertIn("TimeoutError", agent.trace["x"]["fallback_reason"])
                self.assertEqual(agent.model_calls, 0)
                store.apply(
                    [{"parent_asin": "A", "revision": 1, "operation": "delete"}]
                )
                with patch(
                    "search_runtime.intent.PhraseMatcher.match",
                    side_effect=TimeoutError("deadline"),
                ):
                    result = agent.respond("x", "I prefer red", 2, 10)
                self.assertEqual(agent.trace["x"]["version"], 1)
                self.assertNotIn(
                    "A", [r["parent_asin"] for r in result["recommendations"]]
                )
            finally:
                store.close()

    def test_converter_uses_only_active_evidence_and_fails_unknown_values(self):
        from search_runtime.catalog import Catalog

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "catalog.jsonl"
            write_jsonl(path, [product("A", "red")])
            store = Catalog(root / "store", path)
            try:
                converter = Converter(store)
                category = next(iter(converter.categories))
                state = parse(
                    "I need " + category + ". The important part is cotton.",
                    ShoppingState(),
                    converter,
                    1,
                    time.perf_counter() + 1,
                )
                self.assertEqual([c.value for c in state.constraints], ["cotton"])
                with self.assertRaises(ValueError):
                    parse(
                        "I need " + category + ". It must levitate.",
                        ShoppingState(),
                        converter,
                        1,
                        time.perf_counter() + 1,
                    )
                store.apply(
                    [{"parent_asin": "A", "revision": 1, "operation": "delete"}]
                )
                converter.refresh()
                self.assertEqual(converter.values, set())
            finally:
                store.close()

    def test_converter_preserves_punctuation_and_updates_only_changed_products(self):
        from search_runtime.catalog import Catalog

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "catalog.jsonl"
            a = product("A", "red")
            a["features"] = ["100% Cotton", "Closure Type: Pull On"]
            write_jsonl(path, [a, product("B", "blue")])
            store = Catalog(root / "store", path)
            try:
                converter = Converter(store)
                before = converter.processed_products
                state = parse(
                    "My preferences are 100% Cotton; Closure Type: Pull On.",
                    ShoppingState(category="shirts"),
                    converter,
                    2,
                    time.perf_counter() + 1,
                )
                self.assertEqual(
                    [c.value for c in state.constraints],
                    ["100% cotton", "closure type: pull on"],
                )
                store.apply(
                    [{"parent_asin": "A", "revision": 1, "operation": "delete"}]
                )
                converter.refresh()
                self.assertEqual(converter.processed_products - before, 1)
                self.assertIn("cotton", converter.values)
                self.assertNotIn("closure type: pull on", converter.values)
            finally:
                store.close()

    def test_matrix_worker_publication_updates_converter_before_acknowledging(self):
        from search_runtime.catalog import Catalog
        from search_runtime.service import Pool
        import time

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "catalog.jsonl"
            write_jsonl(path, [product("A", "red"), product("B", "blue")])
            store = Catalog(root / "store", path)
            store.close()
            pool = Pool(1, root / "store", variant="rules")
            try:
                deadline = time.monotonic() + 30
                while not pool.ready and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pool.ready)
                self.assertEqual(
                    pool.submit({"operation": "reset", "session_id": "x"})["status"],
                    200,
                )
                request = {
                    "operation": "respond",
                    "session_id": "x",
                    "request_id": "one",
                    "turn": 1,
                    "top_k": 10,
                    "message": "I need shirts. The important part is color: red.",
                }
                self.assertEqual(pool.submit(request)["status"], 200)
                update = pool.publish(
                    [{"parent_asin": "A", "revision": 1, "operation": "delete"}]
                )
                self.assertEqual(update["result"]["worker_acknowledgements"], [1])
                retry = pool.submit(request)
                self.assertEqual(retry["result"]["recommendations"], [])
            finally:
                pool.close()
