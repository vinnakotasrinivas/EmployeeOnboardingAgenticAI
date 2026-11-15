"""Ask OnboardIQ a question from the command line.

Run: uv run python scripts/ask.py "How many PTO days do US employees get per year?"
"""

from __future__ import annotations

import sys
import textwrap
import time

from app.agents.graph import answer_question


def main() -> None:
    try:
        question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Question: ")
    except EOFError:  # Windows PowerShell drops an empty "" argument and there is no stdin
        question = ""
    start = time.perf_counter()
    result = answer_question(question)
    elapsed = time.perf_counter() - start

    print(f"\nQ: {question}\n")
    print("\n".join(textwrap.fill(line, width=100) for line in result["answer"].splitlines()))
    print(f"\nConfidence: {result['confidence']}  |  refused: {result['refused']}  |  {elapsed:.1f}s")

    if result["citations"]:
        print("\nSources:")
        for c in result["citations"]:
            print(f"  [{c['source']}, {c['location']}]  score {c['score']:.2f}")
            print(f"      {c['snippet'][:150]}")

    print("\nAgent steps:")
    for step in result["trace"]:
        print(f"  {step['agent']:<13} {step['ms']:>6} ms  {step['summary']}")


if __name__ == "__main__":
    main()
