from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.agents.context import build_context, cited_labels, format_context, match_citations, timed
from app.agents.prompts import REFUSAL, VALIDATOR
from app.agents.state import AgentState
from app.llm.groq_client import invoke_json

MAX_ATTEMPTS = 2


class Validation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    has_citations: bool


def validate_draft(question: str, draft: str, items: list) -> Validation:
    if REFUSAL.rstrip(".") in draft:
        return Validation(grounded=True, has_citations=False)
    if not cited_labels(draft):
        return Validation(grounded=False, unsupported_claims=["The answer has no citations."], has_citations=False)
    # Only send the blocks the draft cites: halves the tokens and checks the citations point somewhere real.
    cited = match_citations(draft, items) or items
    user = f"Context:\n\n{format_context(cited)}\n\nQuestion: {question}\n\nDraft answer:\n{draft}"
    result = invoke_json([("system", VALIDATOR), ("user", user)], Validation)
    result.has_citations = True
    return result


def validator_node(state: AgentState) -> AgentState:
    with timed("Validator") as t:
        items = build_context(state.get("table_results", []), state.get("retrieved", []))
        result = validate_draft(state["question"], state["draft"], items)
        if result.grounded:
            t["summary"] = "grounded" if result.has_citations else "answer is a refusal; nothing to check"
        else:
            retry = state.get("attempt", 1) < MAX_ATTEMPTS
            t["summary"] = (
                f"{len(result.unsupported_claims)} unsupported claim(s); "
                + ("asking Reasoner to retry" if retry else "giving up and refusing")
            )
    feedback = "\n".join(f"- {c}" for c in result.unsupported_claims)
    return {"validation": result.model_dump(), "feedback": feedback, "trace": [t["step"]]}
