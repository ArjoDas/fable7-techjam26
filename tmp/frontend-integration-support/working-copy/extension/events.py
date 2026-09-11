"""Structured customer turns and canonical protocol rendering."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Event:
    kind: str
    category: str = ""
    values: tuple = ()
    attribute: str = ""


def decode(text):
    if text.startswith("I'm looking for "):
        body = text[len("I'm looking for ") :]
        if body.endswith(", but I'm still exploring."):
            return Event("browse", body[: -len(", but I'm still exploring.")])
        if ". A key requirement is: " in body:
            category, value = body.split(". A key requirement is: ", 1)
            return Event("opening", category, (value[:-1],))
        category, value = body.split(". ", 1)
        return Event("opening_old", category, (value,))
    if text.startswith("For that, what matters is: "):
        return Event(
            "disclosure",
            values=tuple(text[len("For that, what matters is: ") : -1].split("; ")),
        )
    if text.startswith("Actually, ignore my earlier preference. What I need is: "):
        return Event(
            "override",
            values=(
                text[
                    len("Actually, ignore my earlier preference. What I need is: ") : -1
                ],
            ),
        )
    match = re.fullmatch(
        "I don't have a preference for (.+); please use your judgment\\.", text
    )
    if match:
        return Event("boundary", attribute=match[1])
    match = re.fullmatch("I don't have an additional preference for (.+)\\.", text)
    if match:
        return Event("missing", attribute=match[1])
    if (
        text
        == "Those options are not quite right yet. Ask me about one specific attribute."
    ):
        return Event("ask")
    raise ValueError("Unrecognized official event")


def canonical(event):
    e = event
    if e.kind == "opening":
        return f"I'm looking for {e.category}. A key requirement is: {e.values[0]}."
    if e.kind == "opening_old":
        return f"I'm looking for {e.category}. {e.values[0]}"
    if e.kind == "browse":
        return f"I'm looking for {e.category}, but I'm still exploring."
    if e.kind == "disclosure":
        return "For that, what matters is: " + "; ".join(e.values) + "."
    if e.kind == "override":
        return (
            "Actually, ignore my earlier preference. What I need is: "
            + e.values[0]
            + "."
        )
    if e.kind == "boundary":
        return f"I don't have a preference for {e.attribute}; please use your judgment."
    if e.kind == "missing":
        return f"I don't have an additional preference for {e.attribute}."
    if e.kind == "ask":
        return "Those options are not quite right yet. Ask me about one specific attribute."
    raise ValueError(e.kind)
