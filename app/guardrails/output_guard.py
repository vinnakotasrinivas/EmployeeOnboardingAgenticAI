from __future__ import annotations

import re

from app.agents.context import cited_labels
from app.agents.prompts import NO_DOCUMENTS, REFUSAL
from app.guardrails.input_guard import GuardResult
from app.guardrails.moderation import moderate
from app.llm.groq_client import strip_think

_SYSTEM_LINE = re.compile(r"^\s*system\s*:.*$", re.IGNORECASE | re.MULTILINE)


def clean(answer: str) -> str:
    text = _SYSTEM_LINE.sub("", strip_think(answer))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def check_output(answer: str, refused: bool) -> tuple[str, GuardResult]:
    """Return the answer to show and what the guard did. Refusals and error messages pass through."""
    text = clean(answer)
    if refused or text in (REFUSAL, NO_DOCUMENTS):
        return text, GuardResult(allowed=True, reason_code="refusal")
    if not cited_labels(text):
        return REFUSAL, GuardResult(allowed=False, reason_code="no_citations", user_message=REFUSAL)
    safe, _ = moderate(text, "assistant")
    if not safe:
        return REFUSAL, GuardResult(allowed=False, reason_code="unsafe", user_message=REFUSAL)
    return text, GuardResult(allowed=True, reason_code="ok")
