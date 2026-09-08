from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SessionRecord:
    session_id: str
    mode: Literal["internals", "demo"]
    profile: dict[str, Any]
    turn: int = 0
    created_at: float = field(default_factory=time.monotonic)
    last_accessed_at: float = field(default_factory=time.monotonic)
    in_flight: bool = False
    options: dict[str, dict[str, Any]] = field(default_factory=dict)


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self.records: dict[str, SessionRecord] = {}
        self.lock = asyncio.Lock()

    async def create(self, mode: str, profile: dict[str, Any]) -> SessionRecord:
        async with self.lock:
            session_id = str(uuid.uuid4())
            record = SessionRecord(session_id, mode, dict(profile))
            self.records[session_id] = record
            return record

    async def get(self, session_id: str) -> SessionRecord | None:
        async with self.lock:
            record = self.records.get(session_id)
            if record is not None:
                record.last_accessed_at = time.monotonic()
            return record

    async def begin_turn(self, session_id: str) -> tuple[SessionRecord, int]:
        async with self.lock:
            record = self.records.get(session_id)
            if record is None:
                raise KeyError("session_not_found")
            if record.in_flight:
                raise RuntimeError("turn_in_progress")
            if record.turn >= 10:
                raise RuntimeError("turn_limit_reached")
            record.in_flight = True
            record.last_accessed_at = time.monotonic()
            return record, record.turn + 1

    async def finish_turn(
        self, session_id: str, turn: int, *, success: bool
    ) -> SessionRecord | None:
        async with self.lock:
            record = self.records.get(session_id)
            if record is None:
                return None
            if success:
                record.turn = turn
            record.in_flight = False
            record.last_accessed_at = time.monotonic()
            return record

    async def replace_options(
        self, session_id: str, options: list[dict[str, Any]]
    ) -> None:
        async with self.lock:
            record = self.records[session_id]
            record.options = {str(option["id"]): option for option in options}

    async def resolve_option(self, session_id: str, option_id: str) -> str | None:
        async with self.lock:
            record = self.records.get(session_id)
            if record is None:
                return None
            option = record.options.get(option_id)
            return None if option is None else str(option["message_preview"])

    async def reset(self, session_id: str) -> SessionRecord | None:
        async with self.lock:
            record = self.records.get(session_id)
            if record is None:
                return None
            record.turn = 0
            record.in_flight = False
            record.options = {}
            record.last_accessed_at = time.monotonic()
            return record

    async def expired_ids(self) -> list[str]:
        now = time.monotonic()
        async with self.lock:
            expired = [
                session_id
                for session_id, record in self.records.items()
                if not record.in_flight
                and now - record.last_accessed_at > self.ttl_seconds
            ]
            for session_id in expired:
                self.records.pop(session_id, None)
            return expired

