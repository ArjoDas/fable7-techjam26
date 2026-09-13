from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from starter.cp5_dialogue import coarse_category


def _short(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _category_label(categories: object) -> str:
    if not isinstance(categories, list):
        return ""
    values = [str(value).strip() for value in categories if str(value).strip()]
    return values[-1] if values else ""


class ProductCatalog:
    """Full catalog items with normalized display metadata."""

    def __init__(self, catalog_path: str | Path) -> None:
        self.cards: dict[str, dict[str, Any]] = {}
        counts: Counter[str] = Counter()
        labels: dict[str, str] = {}
        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                categories = product.get("categories")
                category_value = " ".join(coarse_category(categories).lower().split())
                category_label = _category_label(categories) or "Products"
                counts[category_value] += 1
                labels.setdefault(category_value, category_label)
                features = product.get("features")
                feature = ""
                if isinstance(features, list) and features:
                    feature = _short(features[0], 150)
                try:
                    price = (
                        float(product["price"])
                        if product.get("price") not in (None, "")
                        else None
                    )
                except (TypeError, ValueError):
                    price = None
                try:
                    rating = (
                        float(product["average_rating"])
                        if product.get("average_rating") not in (None, "")
                        else None
                    )
                except (TypeError, ValueError):
                    rating = None
                try:
                    rating_number = (
                        int(product["rating_number"])
                        if product.get("rating_number") not in (None, "")
                        else None
                    )
                except (TypeError, ValueError):
                    rating_number = None
                self.cards[asin] = {
                    "parent_asin": asin,
                    "title": str(product.get("title") or asin),
                    "price": price,
                    "store": str(product.get("store") or ""),
                    "average_rating": rating,
                    "rating_number": rating_number,
                    "category": _short(category_label, 70),
                    "feature": feature,
                    "features": product.get("features") or [],
                    "description": product.get("description") or [],
                    "categories": categories or [],
                    "details": product.get("details") or {},
                }
        self.categories = [
            {"value": value, "label": labels[value], "count": count}
            for value, count in counts.most_common(18)
            if value
        ]

    @property
    def size(self) -> int:
        return len(self.cards)

    def hydrate(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hydrated: list[dict[str, Any]] = []
        for recommendation in recommendations[:10]:
            asin = str(recommendation.get("parent_asin") or "")
            card = self.cards.get(asin)
            if card is not None:
                hydrated.append(dict(card))
        return hydrated

