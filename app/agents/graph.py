from __future__ import annotations

import functools
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.analyst import analyst_node
from app.agents.context import build_context, match_citations, timed
from app.agents.planner import planner_node
from app.agents.prompts import NO_DOCUMENTS, REFUSAL
from app.agents.reasoner import reasoner_node
from app.agents.retriever import retriever_node
from app.agents.state import AgentState, ContextItem
from app.agents.validator import MAX_ATTEMPTS, validator_node
from app.guardrails.input_guard import check_input
from app.guardrails.output_guard import check_output
from app.guardrails.pii import mask_pii
from app.llm.errors import LLMAuthError, LLMError, LLMRateLimitError
from app.store import tables, vector_store

logger = logging.getLogger("onboardiq.agents")

HIGH_SCORE = 0.6
MEDIUM_SCORE = 0.45
SNIPPET_CHARS = 240
UNEXPECTED = "Something went wrong while answering. Please try again."


def _confidence(items: list[ContextItem], grounded: bool) -> str:
    top = max((i["score"] for i in items), default=0.0)
    if grounded and top >= HIGH_SCORE:
        return "High"
    if grounded and top >= MEDIUM_SCORE:
        return "Medium"
    return "Low"


def _citation(item: ContextItem) -> dict[str, Any]:
    page = re.fullmatch(r"p\.(\d+)", item["location"])
    where = {"page": int(page.group(1))} if page else {"rows": item["location"]}
    snippet = " ".join(item["text"].split())[:SNIPPET_CHARS]
    return {"source": item["source"], **where, "location": item["location"], "snippet": snippet, "score": item["score"]}


def refuse_node(state: AgentState) -> AgentState:
    with timed("Answer") as t:
        t["summary"] = "no relevant context found; refused without calling the Reasoner"
    return {"final_answer": REFUSAL, "refused": True, "confidence": "Low", "citations": [], "trace": [t["step"]]}


def finalize_node(state: AgentState) -> AgentState:
    validation = state.get("validation", {})
    draft = state.get("draft", "")
    with timed("Answer") as t:
        if REFUSAL.rstrip(".") in draft or not validation.get("grounded"):
            t["summary"] = "refused: " + ("not in the documents" if validation.get("grounded") else "answer not grounded")
            update = {"final_answer": REFUSAL, "refused": True, "confidence": "Low", "citations": []}
        else:
            items = build_context(state.get("table_results", []), state.get("retrieved", []))
            cited = match_citations(draft, items)
            confidence = _confidence(cited or items, grounded=True)
            t["summary"] = f"{confidence} confidence, {len(cited)} cited source(s)"
            update = {"final_answer": draft, "refused": False, "confidence": confidence,
                      "citations": [_citation(i) for i in cited]}
    return {**update, "trace": [t["step"]]}


def _after_retriever(state: AgentState) -> str:
    if state["plan"].get("needs_tables"):
        return "analyst"
    return _after_context(state)


def _after_context(state: AgentState) -> str:
    return "reasoner" if state.get("retrieved") or state.get("table_results") else "refuse"


def _after_validator(state: AgentState) -> str:
    if not state["validation"]["grounded"] and state.get("attempt", 1) < MAX_ATTEMPTS:
        return "reasoner"
    return "finalize"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("reasoner", reasoner_node)
    graph.add_node("validator", validator_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retriever")
    graph.add_conditional_edges("retriever", _after_retriever, ["analyst", "reasoner", "refuse"])
    graph.add_conditional_edges("analyst", _after_context, ["reasoner", "refuse"])
    graph.add_edge("reasoner", "validator")
    graph.add_conditional_edges("validator", _after_validator, ["reasoner", "finalize"])
    graph.add_edge("refuse", END)
    graph.add_edge("finalize", END)
    return graph.compile()


@functools.cache
def _compiled():
    return build_graph()


def _result(state: AgentState, **overrides) -> dict[str, Any]:
    result = {
        "answer": state.get("final_answer", REFUSAL),
        "confidence": state.get("confidence", "Low"),
        "refused": state.get("refused", True),
        "citations": state.get("citations", []),
        "trace": state.get("trace", []),
        "attempts": state.get("attempt", 0),
        "error": None,
    }
    return {**result, **overrides}


def _error_code(exc: LLMError) -> str:
    if isinstance(exc, LLMRateLimitError):
        return "rate_limit"
    if isinstance(exc, LLMAuthError):
        return "auth"
    return "llm_unavailable"


def _run_graph(question: str) -> dict[str, Any]:
    if vector_store.stats()["chunks"] == 0 and not tables.all_tables():
        step = {"agent": "Answer", "summary": "knowledge base is empty; no LLM call made", "ms": 0}
        return _result({}, answer=NO_DOCUMENTS, trace=[step])

    state: AgentState = {"question": question, "attempt": 0, "trace": []}
    try:
        for state in _compiled().stream(state, stream_mode="values"):
            pass
    except LLMError as exc:
        logger.warning("LLM error while answering: %s", exc.user_message)
        step = {"agent": "Error", "summary": exc.user_message, "ms": 0}
        return _result(state, answer=exc.user_message, refused=True, confidence="Low", citations=[],
                       trace=[*state.get("trace", []), step], error=_error_code(exc))
    except Exception:
        logger.exception("Unexpected error while answering %r", mask_pii(question))
        step = {"agent": "Error", "summary": UNEXPECTED, "ms": 0}
        return _result(state, answer=UNEXPECTED, refused=True, confidence="Low", citations=[],
                       trace=[*state.get("trace", []), step], error="unexpected")
    return _result(state)


def answer_question(question: str | None) -> dict[str, Any]:
    """Input guard -> agent graph -> output guard."""
    question = (question or "").strip()
    with timed("InputGuard") as t:
        verdict = check_input(question)
        t["summary"] = "passed" if verdict.allowed else f"blocked: {verdict.reason_code}"
    logger.info("Question (%s): %s", verdict.reason_code, mask_pii(question[:300]))
    if not verdict.allowed:
        return _result({}, answer=verdict.user_message, trace=[t["step"]])

    result = _run_graph(question)
    with timed("OutputGuard") as out:
        answer, guard = check_output(result["answer"], result["refused"])
        out["summary"] = {
            "ok": "passed",
            "refusal": "refusal or error passed through",
            "no_citations": "answer had no citations; replaced with refusal",
            "unsafe": "answer flagged unsafe; replaced with refusal",
        }[guard.reason_code]
    if not guard.allowed:
        result.update(refused=True, confidence="Low", citations=[])
    result.update(answer=answer, trace=[t["step"], *result["trace"], out["step"]])
    logger.info("Answer (%s, refused=%s): %s", result["confidence"], result["refused"], mask_pii(answer[:300]))
    return result
