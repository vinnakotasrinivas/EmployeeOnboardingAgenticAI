from __future__ import annotations

import functools
import logging
from pathlib import PurePath
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.ingestion.models import LoadResult
from app.llm.errors import LLMError
from app.llm.groq_client import invoke_json
from app.store.embeddings import embed_texts

logger = logging.getLogger(__name__)

PROFILE_MAX_CHARS = 3000
PROFILE_PAGES = 2
PROFILE_ROWS = 5

ONBOARDING_CATEGORIES: dict[str, str] = {
    "hr_policy": "Employee handbook, HR policies, working hours, remote work, performance and conduct rules.",
    "benefits": "Health insurance, retirement plans such as 401(k) or PF, perks and benefits enrollment.",
    "it_setup_security": "Laptop and account setup, VPN, MFA, passwords, acceptable use and IT security policy.",
    "code_of_conduct": "Code of conduct, ethics, anti-harassment, conflicts of interest and reporting concerns.",
    "team_directory": "Employee or team directory with names, roles, managers, buddies and contact details.",
    "training_schedule": "Training courses, mandatory learning, session schedules and new hire course assignments.",
    "onboarding_checklist": "New hire checklist of tasks with owners and due dates for the first days and weeks.",
    "payroll_leave": "Payroll, pay dates, payslips, tax forms, paid time off, holidays and leave policies.",
    "facilities_faq": "Office locations, facilities, badges, parking, first-week FAQ and how-to guides.",
    "other": "Anything that is not about joining or working at the company (recipes, sports, sales data, etc.).",
}

Decision = Literal["ingest", "reject", "pending"]


class RelevanceDecision(BaseModel):
    relevant: bool
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(max(float(value), 0.0), 1.0)

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        value = value.strip().lower()
        return value if value in ONBOARDING_CATEGORIES else "other"


_CATEGORY_LINES = "\n".join(f"- {name}: {desc}" for name, desc in ONBOARDING_CATEGORIES.items())

SYSTEM_PROMPT = f"""You are the document intake reviewer for an employee onboarding assistant.
Decide whether an uploaded document is useful for answering new employees' questions about joining
and working at the company. You see a short profile: the filename and the start of the content.

Categories:
{_CATEGORY_LINES}

Rules:
- relevant=true only if the document helps a new hire (policies, benefits, IT setup, people, training,
  checklists, pay and leave, facilities, onboarding FAQs). Pick the single best category.
- General business data with no onboarding purpose (sales figures, financial reports, marketing plans,
  product specs) is NOT relevant, even if it comes from the same company. Use category "other".
- Personal, hobby or unrelated content (recipes, sports, news, fiction) is NOT relevant. Use "other".
- Calibrate confidence: 0.9-1.0 when the content is clearly one way, 0.5-0.75 when unsure or mixed,
  below 0.5 when you are mostly guessing.
- reason: one short sentence a user can read, citing what in the profile drove the decision.

Examples:
- "team_directory.csv" with columns employee_id, manager_name, onboarding_buddy_name ->
  relevant=true, category=team_directory, confidence=0.97
- "quarterly_sales.csv" with columns region, quarter, revenue ->
  relevant=false, category=other, confidence=0.9
- "pasta_recipe.txt" describing ingredients and cooking steps ->
  relevant=false, category=other, confidence=0.98"""

# bge cosine scores rarely reach the 0.75 relevance threshold, so fallback decisions land in
# "pending" and a person confirms them; the fallback only suggests a category.
EMBEDDING_RELEVANT_SCORE = 0.45


def build_profile(filename: str, load_result: LoadResult) -> str:
    name = PurePath(filename).name
    parts = [f"Filename: {name}"]
    if load_result.tables:
        for key, df in load_result.tables.items():
            sheet = key.split(":", 1)[1]
            parts.append(f"\nSheet: {sheet} ({len(df)} rows)")
            parts.append("Columns: " + ", ".join(map(str, df.columns)))
            parts.append(df.head(PROFILE_ROWS).to_markdown(index=False))
    else:
        for doc in load_result.docs[:PROFILE_PAGES]:
            page = doc.metadata.get("page")
            parts.append(f"\n[Page {page}]" if page else "")
            parts.append(doc.text)
    profile = "\n".join(p for p in parts if p)
    return profile[:PROFILE_MAX_CHARS]


@functools.cache
def category_vectors() -> tuple[list[str], np.ndarray]:
    names = [c for c in ONBOARDING_CATEGORIES if c != "other"]
    return names, embed_texts([ONBOARDING_CATEGORIES[c] for c in names])


def classify_by_embedding(profile: str) -> RelevanceDecision:
    names, vectors = category_vectors()
    scores = vectors @ embed_texts([profile])[0]
    best = int(np.argmax(scores))
    score = float(scores[best])
    if score >= EMBEDDING_RELEVANT_SCORE:
        return RelevanceDecision(
            relevant=True,
            category=names[best],
            confidence=score,
            reason=f"fallback: closest onboarding category is {names[best]} (similarity {score:.2f}).",
        )
    return RelevanceDecision(
        relevant=False,
        category="other",
        confidence=score,
        reason=f"fallback: not similar to any onboarding category (best {names[best]}, {score:.2f}).",
    )


def classify(profile: str) -> RelevanceDecision:
    if not settings.groq_api_key.strip():
        return classify_by_embedding(profile)
    try:
        decision = invoke_json([("system", SYSTEM_PROMPT), ("user", profile)], RelevanceDecision)
    except LLMError as exc:
        logger.warning("Relevance LLM failed, using fallback: %s", exc.user_message)
        return classify_by_embedding(profile)
    if not decision.relevant:
        decision.category = "other"
    elif decision.category == "other":
        decision.confidence = min(decision.confidence, settings.relevance_threshold - 0.01)
    return decision


def decide(decision: RelevanceDecision) -> Decision:
    if decision.confidence >= settings.relevance_threshold:
        return "ingest" if decision.relevant else "reject"
    return "pending"
