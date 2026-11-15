from __future__ import annotations

import re

import numpy as np
from pydantic import BaseModel

from app.config import settings
from app.guardrails.moderation import moderate

MIN_CHARS = 3
MAX_CHARS = 1000

MESSAGES = {
    "empty": "Please type a question.",
    "length": f"Questions must be between {MIN_CHARS} and {MAX_CHARS} characters.",
    "injection": "I can only answer questions about your onboarding documents.",
    "unsafe": "I can't help with that request.",
    "off_topic": (
        "I'm your onboarding assistant, so I can answer questions about company policies, benefits, "
        "IT setup, people and schedules from the uploaded documents."
    ),
}

INJECTION_PATTERNS = [
    r"\b(ignore|forget|override)\b.{0,20}\b(previous|prior|above|earlier|all|your)\b.{0,15}\b(instructions?|prompts?|rules|directions)\b",
    r"\bdisregard\b.{0,20}\b(above|previous|prior|instructions?|rules)\b",
    r"\bsystem\s+prompt\b",
    r"\b(reveal|show|print|repeat|output|display|tell me)\b.{0,20}\b(your|the)\b.{0,10}\b(prompt|instructions|rules)\b",
    r"\byou\s+are\s+now\b",
    r"^\s*act\s+as\b",
    r"\bact\s+as\s+(a|an|the)\s+(system|developer|admin(istrator)?|root|jailbroken|unrestricted|unfiltered)\b",
    r"\b(developer|dan|god)\s+mode\b",
    r"\bjailbreak",
    r"\bnew\s+instructions\s*:",
    r"\bpretend\b.{0,30}\b(no|without)\s+(rules|restrictions|limits)\b",
]
_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


class GuardResult(BaseModel):
    allowed: bool
    reason_code: str
    user_message: str = ""


def _block(code: str) -> GuardResult:
    return GuardResult(allowed=False, reason_code=code, user_message=MESSAGES[code])


def is_injection(question: str) -> bool:
    return any(p.search(question) for p in _INJECTION)


def topic_scores(question: str) -> tuple[float, float]:
    """(best similarity to an onboarding category, best FAISS score)."""
    from app.ingestion.relevance import category_vectors
    from app.store import vector_store
    from app.store.embeddings import get_embeddings

    _, vectors = category_vectors()
    topic = float((vectors @ np.asarray(get_embeddings().embed_query(question), dtype=np.float32)).max())
    hits = vector_store.search(question, k=1, threshold=0.0)
    return topic, hits[0][1] if hits else 0.0


def is_off_topic(question: str) -> bool:
    topic, search = topic_scores(question)
    return topic < settings.off_topic_threshold and search < settings.off_topic_search_threshold


def check_input(question: str | None) -> GuardResult:
    text = (question or "").strip()
    if not text:
        return _block("empty")
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        return _block("length")
    if is_injection(text):
        return _block("injection")
    # Local off-topic check runs before the (rate-limited) moderation model call.
    if is_off_topic(text):
        return _block("off_topic")
    safe, _ = moderate(text, "user")
    if not safe:
        return _block("unsafe")
    return GuardResult(allowed=True, reason_code="ok")
