from pathlib import Path
p=Path(__file__).parent/'extension-cleanup/extension/protocol.py'
s=p.read_text();start=s.index('def words(');end=s.index('    def reset(',start)
s=s[:start]+'''class ProtocolGuard:
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

'''+s[end:]
start=s.index('from collections');end=s.index('ATTRS =')
s=s[:start]+'from collections import defaultdict\nimport re\nfrom starter.agent import _normalized_value\n\n'+s[end:]
p.write_text(s)
