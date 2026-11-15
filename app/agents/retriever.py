from __future__ import annotations

from app.agents.context import chunk_item, timed
from app.agents.state import AgentState, ContextItem
from app.config import settings
from app.store import vector_store


def retrieve(sub_queries: list[str], category_hint: str | None) -> list[ContextItem]:
    best: dict[str, tuple] = {}
    for query in sub_queries:
        hits = vector_store.search(query, category=category_hint) if category_hint else []
        if len(hits) < settings.top_k:
            hits = hits + vector_store.search(query)
        for doc, score in hits:
            chunk_id = doc.metadata.get("chunk_id") or doc.page_content[:50]
            if chunk_id not in best or score > best[chunk_id][1]:
                best[chunk_id] = (doc, score)
    ranked = sorted(best.values(), key=lambda pair: pair[1], reverse=True)[: settings.top_k]
    return [chunk_item(doc, score) for doc, score in ranked]


def retriever_node(state: AgentState) -> AgentState:
    plan = state["plan"]
    with timed("Retriever") as t:
        items = retrieve(plan["sub_queries"], plan.get("category_hint"))
        if items:
            sources = sorted({i["source"] for i in items})
            t["summary"] = f"{len(items)} chunks (top {items[0]['score']:.2f}) from {', '.join(sources)}"
        else:
            t["summary"] = "no chunks above the similarity threshold"
    return {"retrieved": items, "trace": [t["step"]]}
