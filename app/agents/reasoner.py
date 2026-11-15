from __future__ import annotations

from datetime import date

from app.agents.context import build_context, cited_labels, format_context, timed
from app.agents.prompts import REASONER, REFUSAL
from app.agents.state import AgentState
from app.llm.groq_client import invoke_text


def draft_answer(question: str, context: str, feedback: str = "") -> str:
    system = REASONER.format(today=date.today().strftime("%A %d %B %Y"), refusal=REFUSAL)
    user = f"Context:\n\n{context}\n\nQuestion: {question}"
    if feedback:
        user += f"\n\nYour previous draft had problems. Fix them and cite every claim:\n{feedback}"
    return invoke_text([("system", system), ("user", user)], temperature=0.1)


def reasoner_node(state: AgentState) -> AgentState:
    attempt = state.get("attempt", 0) + 1
    with timed("Reasoner") as t:
        items = build_context(state.get("table_results", []), state.get("retrieved", []))
        draft = draft_answer(state["question"], format_context(items), state.get("feedback", ""))
        refused = REFUSAL.rstrip(".") in draft
        t["summary"] = (
            f"attempt {attempt}: "
            + ("could not answer from context" if refused else f"{len(cited_labels(draft))} citations")
            + f" ({len(items)} context blocks)"
        )
    return {"draft": draft, "attempt": attempt, "trace": [t["step"]]}
