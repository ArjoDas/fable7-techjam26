"""Protocol-compatible happy path with typed state for unfamiliar conversations."""

from collections import defaultdict
import re
from starter.agent import _normalized_value

ATTRS = "category|material|color|size|style|brand|budget|feature|use_case|other"
OPEN = re.compile(r"I'm looking for (.+?)(?:, but I'm still exploring\.|\. (.+))", re.I)
REPLY = re.compile(r"For that, what matters is: (.+)\.", re.I)
OVERRIDE = re.compile(
    r"Actually, ignore my earlier preference\. What I need is: (.+)\.", re.I
)
EMPTY = re.compile(
    r"I don't have (?:an additional preference for (?:"
    + ATTRS
    + r")\.|a preference for (?:"
    + ATTRS
    + r"); please use your judgment\.)",
    re.I,
)
GENERIC = "Those options are not quite right yet. Ask me about one specific attribute."


class ProtocolGuard:
    """Track whether each turn has compatible active-catalog evidence."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.base = catalog.agent
        self.states = {}
        self.trace = {}
        self._version = -1
        self._prepare()

    def _prepare(self, changed=None):
        if changed is None:
            self.protocol_values = defaultdict(set)
            self.category_ids = defaultdict(set)
            self.product_cards = {}
            changed = list(self.base._dialogue_index.cards)
        for asin in changed:
            previous = self.product_cards.pop(asin, None)
            if previous:
                self.category_ids[previous.category].discard(asin)
                if not self.category_ids[previous.category]:
                    del self.category_ids[previous.category]
                for value in previous.sequence:
                    key = (previous.category, value)
                    self.protocol_values[key].discard(asin)
                    if not self.protocol_values[key]:
                        del self.protocol_values[key]
            card = self.base._dialogue_index.cards.get(asin)
            if card is not None:
                self.product_cards[asin] = card
                self.category_ids[card.category].add(asin)
                for value in card.sequence:
                    self.protocol_values[(card.category, value)].add(asin)
        self._version = self.catalog.version

    def reset(self, session_id, user_profile):
        self.base.reset(session_id, user_profile)
        self.states[session_id] = {
            "protocol": True,
            "category": "",
            "possible": None,
            "constraints": [],
            "messages": [],
            "mode": "buying",
            "turn": 0,
            "seen": set(),
            "profile": user_profile,
            "ask": None,
            "category_alias": "",
            "protocol_history": [],
        }

    def close(self, session_id):
        self.states.pop(session_id, None)
        self.trace.pop(session_id, None)
        self.base._sessions.pop(session_id, None)

    def _protocol(self, state, text, turn):
        if not state["protocol"]:
            return False
        if turn == 1:
            match = OPEN.fullmatch(text)
            if not match:
                return False
            category = _normalized_value(match[1])
            if category not in self.category_ids:
                return False
            state["category"] = category
            possible = self.category_ids[category]
            value = match[2]
            if value:
                value = re.sub(
                    r"^A key requirement is: ", "", value, flags=re.I
                ).rstrip(".")
                for part in value.split(";"):
                    possible = possible & self.protocol_values.get(
                        (category, _normalized_value(part)), set()
                    )
            if not possible:
                return False
            state["possible"] = possible
            return True
        if turn != state["turn"] + 1:
            return False
        state["possible"] = state.get("possible", set()) & self.category_ids.get(
            state["category"], set()
        )
        if not state["possible"]:
            return False
        if EMPTY.fullmatch(text):
            return state["ask"] is not None and bool(
                re.search(r"for " + re.escape(state["ask"]) + r"(?:;|\.)", text)
            )
        if text == GENERIC:
            return state["ask"] is None
        match = OVERRIDE.fullmatch(text) or REPLY.fullmatch(text)
        if not match:
            return False
        possible = (
            self.category_ids[state["category"]]
            if OVERRIDE.fullmatch(text)
            else state["possible"]
        )
        for part in match[1].split(";"):
            possible = possible & self.protocol_values.get(
                (state["category"], _normalized_value(part)), set()
            )
        if not possible:
            return False
        state["possible"] = possible
        return True
