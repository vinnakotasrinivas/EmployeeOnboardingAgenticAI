from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class TraceStep(TypedDict):
    agent: str
    summary: str
    ms: int


class ContextItem(TypedDict):
    """One block of evidence shown to the Reasoner, from FAISS or from the Data Analyst."""

    label: str  # citation label, e.g. "employee_handbook.pdf, p.2" or "team_directory.csv, rows 160"
    source: str
    location: str
    text: str
    score: float
    kind: Literal["chunk", "table"]


class AgentState(TypedDict, total=False):
    question: str
    plan: dict[str, Any]
    retrieved: list[ContextItem]
    table_results: list[ContextItem]
    draft: str
    feedback: str
    citations: list[dict[str, Any]]
    validation: dict[str, Any]
    attempt: int
    final_answer: str
    confidence: Literal["High", "Medium", "Low"]
    refused: bool
    trace: Annotated[list[TraceStep], operator.add]
