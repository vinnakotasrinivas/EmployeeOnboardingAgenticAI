# Step 4: Groq client wrapper

## Spec

**Goal:** one place that talks to Groq. It handles retries, hides model "thinking" output, parses JSON reliably, and confirms the configured models actually exist for your key.

**Files created**
- `app/llm/groq_client.py`
- `app/llm/errors.py`: `LLMUnavailableError`, `LLMAuthError` and `LLMRateLimitError`, each carrying a user-friendly message
- `scripts/check_groq.py`
- `tests/test_groq_client.py` (offline tests only; no network)

**Functions in `groq_client.py`**
- `get_chat(model: str | None = None, temperature: float = 0.1) -> ChatGroq`. Uses `settings.groq_model` and `reasoning_format="hidden"`. If the installed `langchain-groq` version rejects that argument, fall back to `model_kwargs={"reasoning_format": "hidden"}`.
- `strip_think(text: str) -> str`: removes `<think>...</think>` blocks, including an unclosed one at the start, and trims whitespace.
- `invoke_text(messages, model=None, temperature=0.1) -> str`: calls the model with retries and returns cleaned text.
- `invoke_json(messages, schema: type[BaseModel], model=None) -> BaseModel`: tries `with_structured_output(schema)` first. If that fails, falls back to `invoke_text` and extracts the first `{...}` block with a regex, then validates it against the schema.
- **Retries:** use `tenacity` for 3 attempts with exponential backoff (1s, 2s, 4s), only on rate-limit, timeout and connection errors. Never retry auth errors. Map them to the error classes in `errors.py`.
- `list_models() -> list[str]`: GET `https://api.groq.com/openai/v1/models` with the key.
- `check_models() -> dict`: returns `{"key_ok": bool, "chat_model_ok": bool, "guard_model_ok": bool, "message": str}`. The result is cached for the process lifetime. The UI banner will use this later.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (sections "Stack" and "API key handling") and docs/build_guide/04_groq_client.md for the exact spec. This is STEP 4 ONLY: Groq client wrapper.

Add dependencies: `uv add langchain-groq langchain-core tenacity httpx`.

Implement app/llm/errors.py, app/llm/groq_client.py exactly as the spec describes (get_chat, strip_think, invoke_text, invoke_json, list_models, check_models). Settings come from app/config.py. Do not log or print the API key.

Create scripts/check_groq.py that:
1. Prints check_models() result.
2. Lists models containing "qwen" or "llama-guard".
3. Sends "Reply with exactly: OK" via invoke_text and prints the reply and latency.
4. Calls invoke_json with a tiny pydantic schema {answer: str, confidence: float} and prints the parsed object.
If the configured GROQ_MODEL is not in the model list, print the closest available qwen/llama models so I can update .env.

Create tests/test_groq_client.py with offline tests for strip_think (closed tag, unclosed leading tag, no tag) and the JSON regex fallback. Run `uv run pytest -q` and `uv run python scripts/check_groq.py`, and show both outputs.
```

## Checkpoint

```powershell
uv run python scripts/check_groq.py
uv run pytest -q
```

**Expected output:** `key_ok: True`, `chat_model_ok: True`, a reply of `OK` with no `<think>` text, and a parsed JSON object. All tests pass.

## Common problems

- **`chat_model_ok: False`:** Groq's model list changes often. Pick a model from the printed list, update `GROQ_MODEL` in `.env`, and also update the default in `app/config.py` and the master plan's "Stack" section.
- **`guard_model_ok: False`:** that's fine for now. Step 9 falls back to rule-based moderation.
- **`with_structured_output` fails on reasoning models:** the regex fallback is there for exactly this, and the test should prove it works.
- **401 errors:** the key has a typo or a trailing space in `.env`. Regenerate the key on console.groq.com if needed.
