from __future__ import annotations

import asyncio
import time
import tempfile
from search_runtime.catalog import Catalog
from search_runtime.factory import create
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TypeVar

from starter.agent import Agent

from .examples import build_examples
from .guided_options import follow_up_options, opening_options
from .products import ProductCatalog
from .semantic import display_trace

T = TypeVar("T")


class RuntimeNotReady(RuntimeError):
    pass


class AgentRuntime:
    """Own the thread-affine SQLite agent and its display catalog."""

    def __init__(self, catalog_path: str | Path) -> None:
        self.catalog_path = Path(catalog_path)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")
        self.agent: Agent | None = None
        self.products: ProductCatalog | None = None
        self.wrapper = None
        self.store = None
        self._catalog_directory = None
        self.examples: list[dict[str, Any]] = []
        self.status = "initializing"
        self.error: str | None = None
        self.startup_seconds: float | None = None
        self._initialization_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._initialization_task is None:
            self._initialization_task = asyncio.create_task(self._initialize())

    async def _initialize(self) -> None:
        started = time.perf_counter()
        try:
            agent, products, semantic, examples = await self._submit(self._build)
            self.agent = agent
            self.products = products
            self.wrapper = semantic
            self.examples = examples
            self.startup_seconds = round(time.perf_counter() - started, 3)
            self.status = "ready"
        except Exception as exc:
            self.error = str(exc)
            self.status = "error"

    def _build(
        self,
    ) -> tuple[Agent, ProductCatalog, Any, list[dict[str, Any]]]:
        self._catalog_directory = tempfile.TemporaryDirectory(prefix="search-ui-")
        self.store = Catalog(self._catalog_directory.name, self.catalog_path)
        agent = self.store.agent
        agent._enable_trace = True
        products = ProductCatalog(self.catalog_path)
        semantic = create(self.store, "minilm")
        examples = build_examples(agent, products)
        return agent, products, semantic, examples

    async def _submit(self, fn: Callable[[], T]) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn)

    def _require(self) -> tuple[Agent, ProductCatalog]:
        if self.status != "ready" or self.agent is None or self.products is None:
            raise RuntimeNotReady(self.error or "The catalog is still initializing")
        return self.agent, self.products

    @property
    def catalog_size(self) -> int:
        return 0 if self.products is None else self.products.size

    async def reset(self, session_id: str, profile: dict[str, Any]) -> None:
        def operation() -> None:
            agent, _ = self._require()
            self.wrapper.reset(session_id, profile)

        await self._submit(operation)

    async def remove(self, session_id: str) -> None:
        def operation() -> None:
            if self.agent is not None:
                self.wrapper.close(session_id)

        await self._submit(operation)

    async def get_opening_options(self) -> list[dict[str, Any]]:
        def operation() -> list[dict[str, Any]]:
            _, products = self._require()
            return opening_options(products.categories)

        return await self._submit(operation)

    async def catalog_meta(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            _, products = self._require()
            return {"product_count": products.size, "categories": products.categories}

        return await self._submit(operation)

    async def respond(
        self,
        session_id: str,
        message: str,
        turn: int,
        *,
        include_trace: bool,
        semantic: bool = False,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            agent, products = self._require()
            state = agent._sessions[session_id]
            state["turn"] = turn
            response = self.wrapper.respond(session_id, message, turn, 10)
            extension_trace = self.wrapper.trace[session_id]
            agent_message = extension_trace.get("canonical_text") or message
            semantic_trace = (
                display_trace(message, extension_trace, self.wrapper.converter)
                if extension_trace["route"] != "protocol"
                else None
            )
            options = follow_up_options(agent, session_id) if include_trace else []
            trace = state.get("last_trace") if include_trace else None
            if trace is not None:
                trace = {
                    **trace,
                    "input_message": message,
                    "agent_message": agent_message,
                    "semantic": semantic_trace,
                    "extension": extension_trace,
                    "selection": {
                        **trace["selection"],
                        "selected": [
                            r["parent_asin"] for r in response["recommendations"]
                        ],
                        "output_k": len(response["recommendations"]),
                    },
                }
            return {
                "assistant": {
                    "message": str(response.get("message") or ""),
                    "ask_attribute": response.get("ask_attribute"),
                },
                "recommendations": products.hydrate(
                    response.get("recommendations") or []
                ),
                "message_options": options,
                "trace": trace,
            }

        return await self._submit(operation)

    async def shutdown(self) -> None:
        if self._initialization_task is not None:
            await self._initialization_task

        def close() -> None:
            if self.agent is not None:
                self.store.close()
                self._catalog_directory.cleanup()

        await self._submit(close)
        self.executor.shutdown(wait=True, cancel_futures=True)
