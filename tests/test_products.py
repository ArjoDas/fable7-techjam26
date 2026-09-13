import json
import tempfile
import unittest
from pathlib import Path

from api.models import ProductCard
from api.products import ProductCatalog


class FullProductTests(unittest.TestCase):
    def test_hydration_preserves_full_fields_and_caps_at_ten(self):
        product = {
            "title": "Long product title " * 30,
            "store": "Long store name " * 20,
            "features": ["Detailed feature " * 100, "Second feature"],
            "description": ["First paragraph", "Second paragraph"],
            "categories": ["Accessories", "Bags"],
            "details": {"Size": "Large", "Dimensions": {"width": 10}},
            "price": None, "average_rating": None, "rating_number": None,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.jsonl"
            path.write_text("".join(json.dumps({**product, "parent_asin": str(i)}) + "\n" for i in range(12)))
            catalog = ProductCatalog(path)
            hydrated = catalog.hydrate([{"parent_asin": str(i)} for i in range(12)])
        self.assertEqual(len(hydrated), 10)
        for row in hydrated:
            validated = ProductCard(**row).model_dump()
            for key, value in product.items():
                self.assertEqual(validated[key], value)

    def test_missing_optional_content_has_safe_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.jsonl"
            path.write_text(json.dumps({"parent_asin": "A"}) + "\n")
            catalog = ProductCatalog(path)
            row = ProductCard(**catalog.hydrate([{"parent_asin": "A"}])[0])
        self.assertEqual(row.title, "A")
        self.assertEqual(row.features, [])
        self.assertEqual(row.description, [])
        self.assertEqual(row.details, {})
        self.assertIsNone(row.price)
