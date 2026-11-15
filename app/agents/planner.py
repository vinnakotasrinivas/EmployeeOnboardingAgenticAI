from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.context import timed
from app.agents.prompts import PLANNER
from app.agents.state import AgentState
from app.ingestion.relevance import ONBOARDING_CATEGORIES
from app.llm.groq_client import invoke_json
from app.store import tables


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["policy", "people_lookup", "schedule", "mixed"]
    needs_tables: bool
    sub_queries: list[str] = Field(default_factory=list)
    category_hint: str | None = None

    @field_validator("sub_queries")
    @classmethod
    def _one_to_three(cls, value: list[str]) -> list[str]:
        return [q.strip() for q in value if q and q.strip()][:3]

    @field_validator("category_hint")
    @classmethod
    def _known(cls, value: str | None) -> str | None:
        value = (value or "").strip().lower()
        return value if value in ONBOARDING_CATEGORIES and value != "other" else None


def plan_question(question: str) -> Plan:
    table_names = sorted(tables.all_tables())
    categories = ", ".join(c for c in ONBOARDING_CATEGORIES if c != "other")
    system = PLANNER.format(tables=", ".join(table_names) or "none", categories=categories)
    plan = invoke_json([("system", system), ("user", question)], Plan)
    if not plan.sub_queries:
        plan.sub_queries = [question]
    if not table_names:
        plan.needs_tables = False
    return plan


def planner_node(state: AgentState) -> AgentState:
    with timed("Planner") as t:
        plan = plan_question(state["question"])
        n = len(plan.sub_queries)
        t["summary"] = (
            f"{plan.type}, {n} sub-quer{'y' if n == 1 else 'ies'}"
            f"{', needs tables' if plan.needs_tables else ''}"
            f"{f', hint {plan.category_hint}' if plan.category_hint else ''}"
        )
    return {"plan": plan.model_dump(), "trace": [t["step"]]}
