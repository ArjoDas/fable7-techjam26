"""Snapshot and changed-product index splice, ported from evaluated b13df08."""
import json,pickle,sqlite3
from pathlib import Path
from extension.common import sha256,write_json
from starter.agent import Agent

def save_agent(agent, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(directory / 'index.sqlite')
    agent.connection.backup(database)
    database.close()
    state = {key: value for key, value in vars(agent).items() if key not in ('connection', '_sessions', '_exact_cache', '_exact_membership_cache')}
    with (directory / 'state.pkl').open('wb') as stream:
        pickle.dump(state, stream, protocol=5)
    write_json(directory / 'manifest.json', {name: sha256(directory / name) for name in ('index.sqlite', 'state.pkl')})


def load_agent(directory):
    # Only load locally generated trusted artifacts; integrity check is not authentication.
    directory = Path(directory)
    hashes = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in hashes.items():
        if sha256(directory / name) != expected:
            raise ValueError('Snapshot checksum mismatch: ' + name)
    agent = Agent.__new__(Agent)
    with (directory / 'state.pkl').open('rb') as stream:
        vars(agent).update(pickle.load(stream))
    agent.connection = sqlite3.connect(':memory:')
    source = sqlite3.connect(directory / 'index.sqlite')
    source.backup(agent.connection)
    source.close()
    agent._sessions, agent._exact_cache, agent._exact_membership_cache = {}, {}, {}
    return agent


class IncrementalIndex:
    def _splice(self, replacement, changed):
        agent = self.agent
        with agent.connection:
            for asin in changed:
                rowid = self.rowids.get(asin)
                if rowid is not None:
                    agent.connection.execute('DELETE FROM products WHERE rowid=?', (rowid,))
                agent.connection.execute('DELETE FROM evidence_values WHERE parent_asin=?', (asin,))
            agent.connection.executemany('INSERT INTO products VALUES (?,?,?,?,?,?,?,?)', replacement.connection.execute('SELECT * FROM products'))
            agent.connection.executemany('INSERT INTO evidence_values VALUES (?,?)', replacement.connection.execute('SELECT * FROM evidence_values'))
        for field in ('_product_views', '_popularity', '_average_rating'):
            values = getattr(agent, field)
            for asin in changed:
                values.pop(asin, None)
            values.update(getattr(replacement, field))
        index = agent._dialogue_index
        for asin in changed:
            card = index.cards.pop(asin, None)
            if card:
                for length in range(1, len(card.sequence) + 1):
                    key = (card.category, *card.sequence[:length])
                    values = index.prefixes.get(key, [])
                    if asin in values:
                        values.remove(asin)
                    if not values:
                        index.prefixes.pop(key, None)
        index.cards.update(replacement._dialogue_index.cards)
        for key, values in replacement._dialogue_index.prefixes.items():
            index.prefixes.setdefault(key, []).extend(values)
        agent._known_categories = {card.category for card in index.cards.values()}
        agent._max_popularity = max(agent._popularity.values(), default=1.0)
        agent._exact_cache.clear()
        agent._exact_membership_cache.clear()

