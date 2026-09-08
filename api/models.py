from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DemoMode = Literal["internals", "demo"]


class SessionCreate(BaseModel):
    mode: DemoMode = "demo"
    user_profile: dict[str, Any] = Field(default_factory=dict)


class TurnCreate(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    option_id: str | None = Field(default=None, max_length=128)


class MessageOption(BaseModel):
    id: str
    label: str
    message_preview: str
    kind: Literal["opening", "constraint", "no_preference", "override", "intent"]
    estimated_remaining: int | None = None
    intent: Literal["browse", "buy"] | None = None


class ProductCard(BaseModel):
    parent_asin: str
    title: str
    price: float | None = None
    store: str = ""
    average_rating: float | None = None
    rating_number: int | None = None
    category: str = ""
    feature: str = ""


class AssistantMessage(BaseModel):
    message: str
    ask_attribute: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    mode: DemoMode
    turn: int
    max_turns: int = 10
    catalog_size: int
    message_options: list[MessageOption] = Field(default_factory=list)


class TurnResponse(BaseModel):
    session_id: str
    mode: DemoMode
    turn: int
    max_turns: int = 10
    assistant: AssistantMessage
    recommendations: list[ProductCard]
    message_options: list[MessageOption] = Field(default_factory=list)
    trace: dict[str, Any] | None = None


class CategoryMeta(BaseModel):
    value: str
    label: str
    count: int


class CatalogMeta(BaseModel):
    product_count: int
    categories: list[CategoryMeta]


class ReadyResponse(BaseModel):
    status: Literal["initializing", "ready", "error"]
    catalog_size: int | None = None
    startup_seconds: float | None = None
    message: str | None = None
