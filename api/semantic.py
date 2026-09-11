"""Display adapter only. All query mapping is owned by search_runtime.intent."""


def display_trace(message, trace, converter):
    state = trace.get("state", {})
    category = state.get("category", "")
    mapping = trace.get("mapping") or {}
    constraints = state.get("constraints", [])
    values = [c["value"] for c in constraints if not c["negative"]]

    def score(value):
        semantic = mapping.get("score") if mapping.get("value") == value else None
        lexical = float(value.lower() in message.lower())
        return {
            "lexical": lexical,
            "semantic": semantic,
            "score": semantic if semantic is not None else lexical,
        }

    return {
        "input": message,
        "browsing": state.get("mode") == "browsing",
        "override": state.get("event")
        in ("correction", "category_change", "reset_preferences"),
        "no_preference": state.get("event") in ("missing", "boundary"),
        "buy_switch": state.get("event") == "mode_change"
        and state.get("mode") == "buying",
        "encoder_used": bool(mapping),
        "encoder_error": trace.get("fallback_reason"),
        "category_candidates": (
            [{"category": category, **score(category)}] if category else []
        ),
        "chosen_category": category or None,
        "value_candidates": [{"value": v, "support": converter.value_counts.get(v, 0), **score(v)} for v in values],
        "chosen_values": values,
        "canonical_message": trace.get("canonical_text"),
    }
