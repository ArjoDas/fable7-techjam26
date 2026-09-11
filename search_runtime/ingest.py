"""Normalize retained Amazon metadata for provenance-checked registration."""


def normalize(raw, source):
    price = raw.get("price")
    try:
        price = float(price)
    except (ValueError, TypeError):
        price = None
    return {
        key: raw.get(key)
        for key in (
            "parent_asin",
            "title",
            "features",
            "description",
            "details",
            "store",
            "rating_number",
            "average_rating",
        )
    } | {
        "categories": raw.get("categories")
        or [raw.get("main_category") or source.replace("_", " ")],
        "price": price,
        "main_category": raw.get("main_category") or source.replace("_", " "),
        "available": True,
    }
