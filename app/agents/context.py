"""Helpers shared by the agents: trace timing, citation labels and a token-budgeted context."""

from __future__ import annotations

import functools
import re
import time
from contextlib import contextmanager
from typing import Iterator

import tiktoken
from langchain_core.documents import Document

from app.agents.state import ContextItem, TraceStep

# Groq's free tier allows ~8k tokens/minute; table chunks are ~2k tokens each, so cap what we send.
MAX_CHUNK_TOKENS = 1800
MAX_TABLE_TOKENS = 1000

CITATION_RE = re.compile(r"\[([^\[\]]+?\.(?:pdf|txt|csv|xlsx|xls)),\s*([^\[\]]+?)\]", re.IGNORECASE)


@functools.cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def truncate_tokens(text: str, limit: int) -> str:
    """Cut to `limit` tokens on a line boundary (keeps table headers intact)."""
    if count_tokens(text) <= limit:
        return text
    kept, used = [], 0
    for line in text.splitlines():
        cost = count_tokens(line) + 1
        if used + cost > limit:
            break
        kept.append(line)
        used += cost
    return "\n".join(kept) + "\n[...truncated]"


@contextmanager
def timed(agent: str) -> Iterator[dict]:
    """Yields a dict; set ["summary"] inside the block. ["step"] holds the finished TraceStep."""
    box: dict = {"summary": ""}
    start = time.perf_counter()
    yield box
    box["step"] = TraceStep(agent=agent, summary=box["summary"], ms=int((time.perf_counter() - start) * 1000))


def location_of(meta: dict) -> str:
    if meta.get("page"):
        return f"p.{meta['page']}"
    if meta.get("row_start"):
        rows = f"rows {meta['row_start']}-{meta['row_end']}"
        return rows if meta.get("file_type") == "csv" else f"{meta['sheet']}, {rows}"
    return "full text"


def chunk_item(doc: Document, score: float) -> ContextItem:
    source = doc.metadata.get("source", "unknown")
    location = location_of(doc.metadata)
    return ContextItem(
        label=f"{source}, {location}",
        source=source,
        location=location,
        text=doc.page_content,
        score=round(score, 3),
        kind="chunk",
    )


def build_context(table_results: list[ContextItem], retrieved: list[ContextItem]) -> list[ContextItem]:
    """Table results first (exact lookups), then chunks by score, each group within its token budget."""
    selected: list[ContextItem] = []
    for items, budget in ((table_results, MAX_TABLE_TOKENS), (retrieved, MAX_CHUNK_TOKENS)):
        remaining = budget
        for item in items:
            if remaining < 150:
                break
            text = truncate_tokens(item["text"], remaining)
            remaining -= count_tokens(text)
            selected.append({**item, "text": text})
    return selected


def format_context(items: list[ContextItem]) -> str:
    return "\n\n".join(f"### [{item['label']}]\n{item['text']}" for item in items)


def cited_labels(text: str) -> list[tuple[str, str]]:
    return [(src.strip(), loc.strip()) for src, loc in CITATION_RE.findall(text)]


def match_citations(answer: str, items: list[ContextItem]) -> list[ContextItem]:
    """Context items the answer cites, matched on source and location (lenient on spacing and case)."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    cited = {(norm(s), norm(loc)) for s, loc in cited_labels(answer)}
    matched = []
    for item in items:
        key = (norm(item["source"]), norm(item["location"]))
        # Sheet-qualified labels are often shortened by the model ("rows 1-25" for "Sheet, rows 1-25").
        if key in cited or any(s == key[0] and len(loc) > 5 and key[1].endswith(loc) for s, loc in cited):
            matched.append(item)
    return matched
