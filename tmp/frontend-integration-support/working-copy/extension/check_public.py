"""Check compatibility through the shipping wrapper and official evaluator."""

import argparse
import json
import tempfile
from unittest.mock import patch
from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from extension.catalog import Catalog
from extension.factory import create


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    args = parser.parse_args()
    ids, categories, products = catalog_index(args.catalog)
    with tempfile.TemporaryDirectory() as directory:
        store = Catalog(directory, args.catalog)
        try:
            agent = create(store)
            with patch(
                "extension.models.Embeddings.encode",
                side_effect=AssertionError("Unexpected model call"),
            ):
                result = evaluate(
                    agent,
                    load_jsonl("data/public_set.jsonl"),
                    ids,
                    categories,
                    products,
                )
            expected = {
                "hit_rate_at_10": 1.0,
                "mrr": 1.0,
                "mttc": 2.1,
                "recommended_technical_score": 0.978,
            }
            measured = {k: result[k] for k in expected}
            assert measured == expected, measured
            assert agent.model_calls == 0
            print(
                json.dumps(
                    {"metrics": measured, "model_calls": agent.model_calls}, indent=2
                )
            )
        finally:
            store.close()


if __name__ == "__main__":
    main()
