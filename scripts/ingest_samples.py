"""Ingest the sample documents through the full pipeline (no UI needed).

Run: uv run python scripts/ingest_samples.py [--reset] [--include-invalid]
"""

from __future__ import annotations

import argparse
import logging
import shutil
import time

from app.config import PROJECT_ROOT, settings
from app.ingestion.pipeline import ingest_many
from app.store import tables, vector_store

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
ONBOARDING = ("pdf", "txt", "csv", "xlsx")
EXTRA = ("irrelevant", "invalid")


def short(text: str, width: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def reset_data() -> None:
    vector_store.reset(delete_files=True)
    tables.reset()
    settings.registry_db.unlink(missing_ok=True)
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="clear the FAISS index, registry and uploads first")
    parser.add_argument("--include-invalid", action="store_true", help="also ingest irrelevant/ and invalid/")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each stage with timings")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(name)s: %(message)s")

    if args.reset:
        reset_data()

    folders = ONBOARDING + (EXTRA if args.include_invalid else ())
    files = [(p.name, p.read_bytes()) for folder in folders for p in sorted((SAMPLES / folder).iterdir())]

    start = time.perf_counter()
    results = ingest_many(files)
    elapsed = time.perf_counter() - start

    rows = []
    for r in results:
        size = f"{r.pages} pages" if r.pages else (f"{r.rows} rows" if r.rows else "-")
        conf = f"{r.confidence:.2f}" if r.confidence is not None else "-"
        rows.append((r.filename, r.status, r.category or "-", conf, size, str(r.chunks), short(r.message)))

    header = ("filename", "status", "category", "conf", "size", "chunks", "message")
    widths = [max(len(row[i]) for row in rows + [header]) for i in range(6)]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)) + "  message")
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + row[6])

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"\n{len(results)} files in {elapsed:.1f}s: {counts}")
    print("Index:", vector_store.stats(), "| tables:", len(tables.all_tables()))


if __name__ == "__main__":
    main()
