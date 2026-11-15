"""Check the Groq key and models, then make one text call and one JSON call.

Run: uv run python scripts/check_groq.py
"""

from __future__ import annotations

import difflib
import sys
import time

from pydantic import BaseModel

from app.config import settings
from app.llm.errors import LLMError
from app.llm.groq_client import check_models, invoke_json, invoke_text, list_models


class TinyAnswer(BaseModel):
    answer: str
    confidence: float


def main() -> int:
    status = check_models()
    print("check_models():")
    for key, value in status.items():
        print(f"  {key}: {value}")
    if not status["key_ok"]:
        return 1

    models = list_models()
    relevant = [m for m in models if "qwen" in m.lower() or "llama-guard" in m.lower()]
    print("\nModels containing 'qwen' or 'llama-guard':")
    for m in relevant:
        print("  ", m)

    if not status["chat_model_ok"]:
        candidates = [m for m in models if "qwen" in m.lower() or "llama" in m.lower()]
        close = difflib.get_close_matches(settings.groq_model, candidates, n=5, cutoff=0.3) or candidates
        print(f"\nGROQ_MODEL '{settings.groq_model}' not found. Closest available models:")
        for m in close:
            print("  ", m)
        return 1

    print(f"\nText call ({settings.groq_model}):")
    try:
        start = time.perf_counter()
        reply = invoke_text([("user", "Reply with exactly: OK")])
        print(f"  reply: {reply!r}  ({time.perf_counter() - start:.2f}s)")

        start = time.perf_counter()
        parsed = invoke_json(
            [("user", "What is the capital of France? Give your answer and a confidence between 0 and 1.")],
            TinyAnswer,
        )
        print(f"\nJSON call:\n  {parsed!r}  ({time.perf_counter() - start:.2f}s)")
    except LLMError as exc:
        print(f"  failed: {exc.user_message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
