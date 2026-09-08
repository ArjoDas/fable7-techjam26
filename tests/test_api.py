from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.temporary_directory.name) / "catalog.jsonl"
        products = [
            {
                "parent_asin": "A",
                "title": "Black leather belt",
                "categories": ["Accessories", "Belts"],
                "features": ["Full grain leather", "Buckle closure; Imported"],
                "details": {"Department": "mens"},
                "store": "Example",
                "description": ["Everyday belt"],
                "price": 39.99,
                "average_rating": 4.8,
                "rating_number": 200,
            },
            {
                "parent_asin": "B",
                "title": "Blue fabric belt",
                "categories": ["Accessories", "Belts"],
                "features": ["Canvas fabric"],
                "details": {"Department": "mens"},
                "store": "Example",
                "description": ["Casual belt"],
                "price": 19.99,
                "average_rating": 4.3,
                "rating_number": 80,
            },
            {
                "parent_asin": "C",
                "title": "Red running sneakers",
                "categories": ["Shoes", "Athletic Shoes"],
                "features": ["Rubber sole"],
                "details": {"Department": "mens"},
                "store": "Example",
                "description": ["Lightweight trainers"],
                "price": 69.99,
                "average_rating": 4.5,
                "rating_number": 150,
            },
        ]
        self.catalog_path.write_text(
            "".join(json.dumps(product) + "\n" for product in products),
            encoding="utf-8",
        )
        self.client_context = TestClient(
            create_app(catalog_path=self.catalog_path, session_ttl=60)
        )
        self.client = self.client_context.__enter__()
        for _ in range(100):
            response = self.client.get("/readyz")
            if response.status_code == 200:
                break
            time.sleep(0.01)
        self.assertEqual(response.status_code, 200, response.text)

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def test_demo_session_accepts_free_form_and_hydrates_products(self) -> None:
        created = self.client.post("/v1/sessions", json={"mode": "demo"})
        self.assertEqual(created.status_code, 201, created.text)
        session_id = created.json()["session_id"]
        turn = self.client.post(
            f"/v1/sessions/{session_id}/turns",
            json={"message": "Recommend a durable leather belt"},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        payload = turn.json()
        self.assertEqual(payload["turn"], 1)
        self.assertIsNone(payload["trace"])
        self.assertTrue(payload["recommendations"])
        self.assertIn("title", payload["recommendations"][0])

    def test_internals_session_requires_issued_option_and_returns_trace(self) -> None:
        created = self.client.post("/v1/sessions", json={"mode": "internals"})
        payload = created.json()
        self.assertTrue(payload["message_options"])
        self.assertEqual(
            {option["intent"] for option in payload["message_options"]},
            {"browse", "buy"},
        )
        self.assertTrue(
            all(option["label"].startswith(("Explore ", "Shop ")) for option in payload["message_options"])
        )
        session_id = payload["session_id"]
        rejected = self.client.post(
            f"/v1/sessions/{session_id}/turns", json={"option_id": "stale"}
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["error"]["code"], "invalid_option")
        option_id = payload["message_options"][0]["id"]
        turn = self.client.post(
            f"/v1/sessions/{session_id}/turns", json={"option_id": option_id}
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        result = turn.json()
        self.assertEqual(result["trace"]["catalog"]["count"], 3)
        self.assertIn("retrieval", result["trace"])
        self.assertTrue(result["message_options"])
        switch = next(
            option
            for option in result["message_options"]
            if option["kind"] == "intent" and option["intent"] == "buy"
        )
        switched = self.client.post(
            f"/v1/sessions/{session_id}/turns", json={"option_id": switch["id"]}
        )
        self.assertEqual(switched.status_code, 200, switched.text)
        self.assertEqual(switched.json()["session_id"], session_id)
        self.assertEqual(switched.json()["turn"], 2)
        self.assertEqual(
            switched.json()["trace"]["conversation"]["intent_mode"],
            "specific buying",
        )

    def test_server_enforces_ten_turn_limit_and_reset(self) -> None:
        created = self.client.post("/v1/sessions", json={"mode": "demo"}).json()
        session_id = created["session_id"]
        for turn in range(1, 11):
            response = self.client.post(
                f"/v1/sessions/{session_id}/turns",
                json={"message": "Show me another belt"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["turn"], turn)
        blocked = self.client.post(
            f"/v1/sessions/{session_id}/turns",
            json={"message": "One more"},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "turn_limit_reached")
        reset = self.client.post(f"/v1/sessions/{session_id}/reset")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["turn"], 0)

    def test_catalog_metadata_uses_real_counts(self) -> None:
        response = self.client.get("/v1/catalog/meta")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product_count"], 3)
        self.assertEqual(sum(row["count"] for row in response.json()["categories"]), 3)


if __name__ == "__main__":
    unittest.main()
