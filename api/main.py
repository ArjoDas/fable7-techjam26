from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    CatalogMeta,
    ReadyResponse,
    SessionCreate,
    SessionResponse,
    TurnCreate,
    TurnResponse,
)
from .runtime import AgentRuntime, RuntimeNotReady
from .sessions import SessionRecord, SessionStore


def _error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


def _raise(http_status: int, code: str, message: str, retryable: bool = False) -> None:
    raise HTTPException(http_status, detail=_error(code, message, retryable)["error"])


def create_app(
    *, catalog_path: str | Path | None = None, session_ttl: int | None = None
) -> FastAPI:
    resolved_catalog = Path(
        catalog_path or os.getenv("CATALOG_PATH", "data/catalog.jsonl")
    )
    runtime = AgentRuntime(resolved_catalog)
    sessions = SessionStore(
        session_ttl or int(os.getenv("SESSION_TTL_SECONDS", "1800"))
    )

    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            for session_id in await sessions.expired_ids():
                await runtime.remove(session_id)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        runtime.start()
        cleanup = asyncio.create_task(cleanup_loop())
        yield
        cleanup.cancel()
        try:
            await cleanup
        except asyncio.CancelledError:
            pass
        await runtime.shutdown()

    app = FastAPI(
        title="TechJam Shopping Agent API",
        version="1.0.0",
        lifespan=lifespan,
    )
    origins = [
        value.strip()
        for value in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if value.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.runtime = runtime
    app.state.sessions = sessions

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            payload = {"error": exc.detail}
        else:
            payload = _error("request_error", str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=422,
            content=_error("invalid_request", "The request body is invalid"),
        )

    def ensure_ready() -> None:
        if runtime.status == "error":
            _raise(503, "agent_error", runtime.error or "Agent initialization failed", True)
        if runtime.status != "ready":
            _raise(503, "agent_initializing", "The catalog is still initializing", True)

    async def set_options(
        record: SessionRecord, options: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        await sessions.replace_options(record.session_id, options)
        return options

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=ReadyResponse)
    async def ready(request: Request) -> ReadyResponse:
        del request
        payload = ReadyResponse(
            status=runtime.status,
            catalog_size=runtime.catalog_size or None,
            startup_seconds=runtime.startup_seconds,
            message=runtime.error,
        )
        if runtime.status != "ready":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=payload.model_dump(),
            )
        return payload

    @app.get("/v1/catalog/meta", response_model=CatalogMeta)
    async def catalog_meta() -> dict[str, Any]:
        ensure_ready()
        return await runtime.catalog_meta()

    @app.post("/v1/sessions", response_model=SessionResponse, status_code=201)
    async def create_session(body: SessionCreate) -> SessionResponse:
        ensure_ready()
        record = await sessions.create(body.mode, body.user_profile)
        await runtime.reset(record.session_id, record.profile)
        options: list[dict[str, Any]] = []
        if record.mode == "internals":
            options = await set_options(record, await runtime.get_opening_options())
        return SessionResponse(
            session_id=record.session_id,
            mode=record.mode,
            turn=0,
            catalog_size=runtime.catalog_size,
            message_options=options,
        )

    @app.post("/v1/sessions/{session_id}/turns", response_model=TurnResponse)
    async def create_turn(session_id: str, body: TurnCreate) -> TurnResponse:
        ensure_ready()
        record = await sessions.get(session_id)
        if record is None:
            _raise(404, "session_not_found", "Start a new conversation and try again")
        message = (body.message or "").strip()
        if record.mode == "internals":
            if not body.option_id:
                _raise(422, "invalid_option", "Choose one of the available messages")
            resolved = await sessions.resolve_option(session_id, body.option_id)
            if resolved is None:
                _raise(422, "invalid_option", "That option is no longer available")
            message = resolved
        elif not message:
            _raise(422, "invalid_message", "Enter what you are looking for")

        try:
            record, next_turn = await sessions.begin_turn(session_id)
        except KeyError:
            _raise(404, "session_not_found", "Start a new conversation and try again")
        except RuntimeError as exc:
            code = str(exc)
            if code == "turn_in_progress":
                _raise(409, code, "This conversation already has a turn in progress", True)
            _raise(409, code, "This conversation has reached its ten-turn limit")

        try:
            result = await runtime.respond(
                session_id,
                message,
                next_turn,
                include_trace=record.mode == "internals",
            )
        except (RuntimeNotReady, KeyError) as exc:
            await sessions.finish_turn(session_id, next_turn, success=False)
            _raise(503, "agent_error", str(exc), True)
        except Exception:
            await sessions.finish_turn(session_id, next_turn, success=False)
            _raise(500, "agent_error", "The agent could not complete this turn", True)

        record = await sessions.finish_turn(session_id, next_turn, success=True)
        assert record is not None
        options = result["message_options"]
        if record.mode == "internals":
            options = await set_options(record, options)
        return TurnResponse(
            session_id=session_id,
            mode=record.mode,
            turn=record.turn,
            assistant=result["assistant"],
            recommendations=result["recommendations"],
            message_options=options,
            trace=result["trace"],
        )

    @app.post("/v1/sessions/{session_id}/reset", response_model=SessionResponse)
    async def reset_session(session_id: str) -> SessionResponse:
        ensure_ready()
        record = await sessions.reset(session_id)
        if record is None:
            _raise(404, "session_not_found", "Start a new conversation and try again")
        await runtime.reset(session_id, record.profile)
        options: list[dict[str, Any]] = []
        if record.mode == "internals":
            options = await set_options(record, await runtime.get_opening_options())
        return SessionResponse(
            session_id=session_id,
            mode=record.mode,
            turn=0,
            catalog_size=runtime.catalog_size,
            message_options=options,
        )

    return app


app = create_app()
