"""Construct the supported local conversation routes."""

from search_runtime.translate import TranslatedAgent


def create(store, variant="minilm", worker_id=None):
    if variant not in ("rules", "minilm"):
        raise ValueError("Supported routes are rules and minilm")
    return TranslatedAgent(store, mode=variant)
