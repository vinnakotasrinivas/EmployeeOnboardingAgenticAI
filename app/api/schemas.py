from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ingestion.pipeline import IngestResult

__all__ = ["AskRequest", "AskResponse", "DeleteResponse", "DiscardResponse", "Document", "Health", "IngestResult"]


class AskRequest(BaseModel):
    # The input guard enforces the 3-1000 character rule with a friendly message; this only stops abuse.
    question: str = Field(default="", max_length=5000, examples=["How many PTO days do US employees get?"])


class Citation(BaseModel):
    source: str
    location: str
    page: int | None = None
    rows: str | None = None
    snippet: str
    score: float


class TraceStep(BaseModel):
    agent: str
    summary: str
    ms: int


class AskResponse(BaseModel):
    answer: str
    confidence: Literal["High", "Medium", "Low"]
    refused: bool
    citations: list[Citation]
    trace: list[TraceStep]
    latency_ms: int


class Document(BaseModel):
    id: str
    filename: str
    file_type: str | None
    size_bytes: int
    status: Literal["indexed", "rejected", "pending", "error"]
    category: str | None
    confidence: float | None
    reason: str | None
    chunks: int
    created_at: str
    updated_at: str


class DeleteResponse(BaseModel):
    deleted: bool
    chunks_removed: int


class DiscardResponse(BaseModel):
    discarded: bool


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    groq: dict[str, Any]
    chat_model: str
    guard_model: str
    embedding_model: str
    chunks: int
    docs: int
