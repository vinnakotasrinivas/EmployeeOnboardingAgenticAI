"""Index the sample onboarding documents into FAISS and run a few test searches.

Run: uv run python scripts/check_search.py [--reset] [--skip-relevance]
"""

from __future__ import annotations

import argparse
import time

from app.config import PROJECT_ROOT
from app.ingestion.chunker import chunk
from app.ingestion.loaders import load_file
from app.ingestion.relevance import build_profile, classify
from app.ingestion.validator import validate_file
from app.store import vector_store

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
FOLDERS = ("pdf", "txt", "csv", "xlsx")
QUERIES = [
    "How many PTO days do US employees get?",
    "Who is Siddharth Patel's manager?",
    "What happens on day 1 of onboarding?",
    "How do I connect to the VPN?",
]


def location(meta: dict) -> str:
    if "page" in meta:
        return f"p.{meta['page']}"
    if "row_start" in meta:
        sheet = f"{meta['sheet']} " if meta.get("file_type") != "csv" else ""
        return f"{sheet}rows {meta['row_start']}-{meta['row_end']}"
    return ""


def index_samples(skip_relevance: bool) -> None:
    for folder in FOLDERS:
        for path in sorted((SAMPLES / folder).iterdir()):
            data = path.read_bytes()
            if not validate_file(path.name, data).ok:
                print(f"  skip {path.name}: invalid")
                continue
            loaded = load_file(path.name, data)
            if loaded.error:
                print(f"  skip {path.name}: {loaded.error}")
                continue
            category = "unknown" if skip_relevance else classify(build_profile(path.name, loaded)).category
            added = vector_store.add_documents(chunk(loaded, path.stem, category))
            print(f"  {path.name:26} {category:22} {added:3} chunks")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete data/faiss_index before indexing")
    parser.add_argument("--skip-relevance", action="store_true", help="don't call Groq; use category 'unknown'")
    args = parser.parse_args()

    if args.reset:
        vector_store.reset(delete_files=True)
    if vector_store.stats()["chunks"] == 0:
        print("Indexing sample documents:")
        start = time.perf_counter()
        index_samples(args.skip_relevance)
        print(f"Indexed in {time.perf_counter() - start:.1f}s")
    print("Index:", vector_store.stats())

    for query in QUERIES:
        print(f"\nQ: {query}")
        hits = vector_store.search(query, k=5)
        if not hits:
            print("  (no results above threshold)")
        for doc, score in hits:
            snippet = " ".join(doc.page_content.split())[:100]
            print(f"  {score:.3f}  {doc.metadata['source']:24} {location(doc.metadata):30} {snippet}")


if __name__ == "__main__":
    main()
