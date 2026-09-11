"""Durable source-backed product versions and incrementally refreshed readers."""

from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from extension.common import read_jsonl, write_jsonl
from extension.index import IncrementalIndex, save_agent, load_agent
from starter.agent import Agent


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class Catalog(IncrementalIndex):
    def __init__(self, directory, catalog_path=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.metrics = []
        self.db = sqlite3.connect(self.directory / "catalog.sqlite", timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS products(asin TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT);
            CREATE TABLE IF NOT EXISTS registry(asin TEXT, digest TEXT, provenance TEXT, PRIMARY KEY(asin,digest));
            CREATE TABLE IF NOT EXISTS events(version INTEGER PRIMARY KEY, events TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);"""
        )
        initialized = self.db.execute(
            "SELECT value FROM metadata WHERE key='initialized'"
        ).fetchone()
        if not initialized:
            if catalog_path is None:
                raise ValueError("First initialization requires catalog")
            rows = read_jsonl(catalog_path)
            if len({p["parent_asin"] for p in rows}) != len(rows):
                raise ValueError("Duplicate product ID")
            with self.db:
                for p in rows:
                    self.db.execute(
                        "INSERT INTO products VALUES (?,?,?)",
                        (p["parent_asin"], 0, json.dumps(p)),
                    )
                    self.db.execute(
                        "INSERT INTO registry VALUES (?,?,?)",
                        (
                            p["parent_asin"],
                            digest(p),
                            json.dumps({"initial_catalog": str(catalog_path)}),
                        ),
                    )
                self.db.execute("INSERT INTO metadata VALUES ('initialized','1')")
        self.products = {
            a: json.loads(b)
            for a, b in self.db.execute(
                "SELECT asin,body FROM products WHERE body IS NOT NULL"
            )
        }
        self.revisions = dict(self.db.execute("SELECT asin,revision FROM products"))
        self.version = self.db.execute(
            "SELECT COALESCE(MAX(version),0) FROM events"
        ).fetchone()[0]
        snapshot = self.directory / f"snapshot-{self.version}"
        self.agent = None
        if (snapshot / "manifest.json").exists():
            try:
                self.agent = load_agent(snapshot)
            except (ValueError, OSError):
                pass  # Durable authoritative rows recover an interrupted cache checkpoint.
        if self.agent is None:
            self.agent = self._build(self.products)
            save_agent(self.agent, snapshot)
        self._prepare()

    def _prepare(self):
        self.agent.connection.execute(
            "CREATE INDEX IF NOT EXISTS evidence_asin_idx ON evidence_values(parent_asin)"
        )
        self.rowids = dict(
            self.agent.connection.execute("SELECT parent_asin,rowid FROM products")
        )

    def _build(self, products):
        with tempfile.TemporaryDirectory(dir=self.directory) as folder:
            path = Path(folder) / "active.jsonl"
            write_jsonl(
                path, [p for p in products.values() if p.get("available", True)]
            )
            return Agent(path)

    def register(self, records):
        from extension.ingest import normalize

        with self.lock, self.db:
            for row in records:
                if not row["source_url"].startswith(
                    "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/"
                ):
                    raise ValueError("Unapproved product source")
                expected = normalize(row["raw"], row["source_category"])
                if row.get("withdraw_fields"):
                    allowed = {
                        "price",
                        "features",
                        "description",
                        "details",
                        "categories",
                        "store",
                    }
                    if not set(row["withdraw_fields"]) <= allowed:
                        raise ValueError("Unsupported metadata withdrawal")
                    for field in row["withdraw_fields"]:
                        expected[field] = (
                            None
                            if field in ("price", "store")
                            else {} if field == "details" else []
                        )
                if expected != row["product"]:
                    raise ValueError(
                        "Normalized product disagrees with retained source"
                    )
                provenance = {
                    k: row[k]
                    for k in (
                        "source_url",
                        "source_line",
                        "source_record_sha256",
                        "source_category",
                    )
                }
                provenance["raw_canonical_sha256"] = digest(row["raw"])
                provenance["experimental_metadata_withdrawal"] = row.get(
                    "withdraw_fields", []
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO registry VALUES (?,?,?)",
                    (expected["parent_asin"], digest(expected), json.dumps(provenance)),
                )

    def _validate(self, events):
        revisions = dict(self.revisions)
        changed = {}
        accepted = []
        for event in events:
            asin = event["parent_asin"]
            revision = event["revision"]
            op = event["operation"]
            if (
                not isinstance(revision, int)
                or isinstance(revision, bool)
                or revision < 1
            ):
                raise ValueError("Positive integer revision required")
            if op not in ("upsert", "delete", "availability"):
                raise ValueError("Unknown event operation")
            if not self.db.execute(
                "SELECT 1 FROM registry WHERE asin=?", (asin,)
            ).fetchone():
                raise ValueError("Product lacks approved source record")
            if revision <= revisions.get(asin, 0):
                continue
            current = changed.get(asin, self.products.get(asin))
            if op == "upsert":
                p = copy.deepcopy(event["product"])
                if p["parent_asin"] != asin:
                    raise ValueError("Product identity mismatch")
                if "available" in p and not isinstance(p["available"], bool):
                    raise ValueError("Availability must be boolean")
                fact_hash = digest({k: v for k, v in p.items() if k != "available"})
                # Availability is operational state, not a source product fact.
                hashes = (digest(p), fact_hash, digest({**p, "available": True}))
                if not self.db.execute(
                    "SELECT 1 FROM registry WHERE asin=? AND digest IN (?,?,?)",
                    (asin, *hashes),
                ).fetchone():
                    raise ValueError("Product facts lack registered provenance")
                changed[asin] = p
            elif op == "delete":
                changed[asin] = None
            else:
                if current is None or not isinstance(event.get("available"), bool):
                    raise ValueError(
                        "Availability requires existing product and boolean"
                    )
                changed[asin] = {**current, "available": event["available"]}
            revisions[asin] = revision
            accepted.append(event)
        return changed, revisions, accepted

    def _refresh(self, changed):
        replacement = self._build({a: p for a, p in changed.items() if p is not None})
        try:
            self._splice(replacement, changed)
        finally:
            replacement.connection.close()
        for a, p in changed.items():
            if p is None:
                self.products.pop(a, None)
            else:
                self.products[a] = p

    def apply(self, events):
        with self.lock:
            started = time.perf_counter()
            self.sync()
            changed, revisions, accepted = self._validate(events)
            if not changed:
                return self.version
            # Persist authoritative state and outbox atomically. Other readers see
            # only committed transactions and then apply the same derived delta.
            old_products = dict(self.products)
            old_sessions = self.agent._sessions
            try:
                self.db.execute("BEGIN IMMEDIATE")
                latest = self.db.execute(
                    "SELECT COALESCE(MAX(version),0) FROM events"
                ).fetchone()[0]
                if latest != self.version:
                    raise RuntimeError(
                        "Concurrent writer; retry through publication coordinator"
                    )
                self._refresh(changed)
                for a, p in changed.items():
                    self.db.execute(
                        "INSERT OR REPLACE INTO products VALUES (?,?,?)",
                        (a, revisions[a], json.dumps(p) if p is not None else None),
                    )
                version = self.version + 1
                self.db.execute(
                    "INSERT INTO events VALUES (?,?)",
                    (
                        version,
                        json.dumps(
                            {
                                "changed": changed,
                                "revisions": {a: revisions[a] for a in changed},
                                "accepted": accepted,
                            }
                        ),
                    ),
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
                self.agent.connection.close()
                self.products = old_products
                self.agent = self._build(old_products)
                self.agent._sessions = old_sessions
                self._prepare()
                raise
            self.version = version
            self.revisions = revisions
            self.metrics.append(
                {
                    "version": version,
                    "products_changed": len(changed),
                    "derived_product_builds": len(changed),
                    "seconds": time.perf_counter() - started,
                }
            )
            return version

    def sync(self, minimum_version=None):
        with self.lock:
            rows = self.db.execute(
                "SELECT version,events FROM events WHERE version>? ORDER BY version",
                (self.version,),
            ).fetchall()
            for version, payload in rows:
                data = json.loads(payload)
                old = dict(self.products)
                sessions = self.agent._sessions
                try:
                    self._refresh(data["changed"])
                except Exception:
                    self.agent.connection.close()
                    self.products = old
                    self.agent = self._build(old)
                    self.agent._sessions = sessions
                    self._prepare()
                    raise
                self.revisions.update(data["revisions"])
                self.version = version
            if minimum_version is not None and self.version < minimum_version:
                raise RuntimeError("Requested catalog version not yet committed")
            return self.version

    def checkpoint(self):
        with self.lock:
            save_agent(self.agent, self.directory / f"snapshot-{self.version}")

    def close(self):
        self.agent.connection.close()
        self.db.close()
