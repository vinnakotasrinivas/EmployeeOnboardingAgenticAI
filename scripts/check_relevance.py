"""Run the relevance gate on every sample file and print the decisions.

Run: uv run python scripts/check_relevance.py
"""

from __future__ import annotations

import time

from app.config import PROJECT_ROOT
from app.ingestion.loaders import load_file
from app.ingestion.relevance import build_profile, classify, decide
from app.ingestion.validator import validate_file

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
FOLDERS = ("pdf", "txt", "csv", "xlsx", "irrelevant")


def short(text: str, width: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def main() -> None:
    rows = []
    start = time.perf_counter()
    for folder in FOLDERS:
        for path in sorted((SAMPLES / folder).iterdir()):
            data = path.read_bytes()
            check = validate_file(path.name, data)
            if not check.ok:
                rows.append((path.name, "invalid", "-", "-", check.message))
                continue
            loaded = load_file(path.name, data)
            if loaded.error:
                rows.append((path.name, "error", "-", "-", loaded.error))
                continue
            decision = classify(build_profile(path.name, loaded))
            rows.append((path.name, decide(decision), decision.category, f"{decision.confidence:.2f}", decision.reason))

    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    header = ("filename", "decision", "category", "conf")
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)) + "  reason")
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + short(row[4]))
    print(f"\n{len(rows)} files in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
