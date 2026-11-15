from __future__ import annotations

import functools
from pathlib import PurePath

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.loaders import to_markdown
from app.ingestion.models import LoadResult

CHUNK_TOKENS = 700
CHUNK_OVERLAP = 100
TABLE_ROWS_PER_CHUNK = 25


@functools.cache
def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=CHUNK_TOKENS, chunk_overlap=CHUNK_OVERLAP)


def _table_chunks(load_result: LoadResult) -> list[tuple[str, dict]]:
    pieces = []
    for key, df in load_result.tables.items():
        source, sheet = key.split(":", 1)
        file_type = PurePath(source).suffix.lower().lstrip(".")
        for start in range(0, len(df), TABLE_ROWS_PER_CHUNK):
            group = df.iloc[start : start + TABLE_ROWS_PER_CHUNK]
            row_start, row_end = start + 1, start + len(group)
            where = f"rows {row_start}-{row_end}" if file_type == "csv" else f"sheet {sheet}, rows {row_start}-{row_end}"
            text = f"Source: {source}, {where}\n\n{to_markdown(group)}"
            meta = {"source": source, "file_type": file_type, "sheet": sheet, "row_start": row_start, "row_end": row_end}
            pieces.append((text, meta))
    return pieces


def _prose_chunks(load_result: LoadResult) -> list[tuple[str, dict]]:
    pieces = []
    for doc in load_result.docs:
        for text in _splitter().split_text(doc.text):
            pieces.append((text, dict(doc.metadata)))
    return pieces


def chunk(load_result: LoadResult, doc_id: str, category: str) -> list[Document]:
    pieces = _table_chunks(load_result) if load_result.tables else _prose_chunks(load_result)
    documents = []
    for n, (text, meta) in enumerate(pieces):
        meta.update(doc_id=doc_id, category=category, chunk_id=f"{doc_id}:{n}")
        documents.append(Document(page_content=text, metadata=meta, id=meta["chunk_id"]))
    return documents
