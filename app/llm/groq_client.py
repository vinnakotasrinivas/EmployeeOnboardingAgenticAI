from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Sequence, TypeVar

import groq
import httpx
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError
from tenacity import RetryCallState, retry, retry_if_exception, wait_exponential

from app.config import settings
from app.llm.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMUnavailableError

logger = logging.getLogger(__name__)

MODELS_URL = "https://api.groq.com/openai/v1/models"
REQUEST_TIMEOUT_S = 60
MAX_RETRY_AFTER_S = 20
RATE_LIMIT_ATTEMPTS = 6
MAX_RATE_LIMIT_WAIT_S = 60

T = TypeVar("T", bound=BaseModel)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"^\s*<think>.*", re.DOTALL | re.IGNORECASE)
_RETRYABLE = (groq.RateLimitError, groq.APITimeoutError, groq.APIConnectionError, groq.InternalServerError)


def _api_key() -> str:
    key = settings.groq_api_key.strip()
    if not key:
        raise LLMAuthError()
    return key


def get_chat(
    model: str | None = None, temperature: float = 0.1, hide_reasoning: bool = True, **extra: Any
) -> ChatGroq:
    """`hide_reasoning=False` is for models that reject `reasoning_format` (Llama Guard, gpt-oss)."""
    kwargs: dict[str, Any] = {
        "model": model or settings.groq_model,
        "temperature": temperature,
        "api_key": _api_key(),
        "timeout": REQUEST_TIMEOUT_S,
        "max_retries": 0,
        "max_tokens": settings.groq_max_tokens,
        **extra,
    }
    if not hide_reasoning:
        return ChatGroq(**kwargs)
    try:
        return ChatGroq(**kwargs, reasoning_format="hidden")
    except (TypeError, ValidationError):
        return ChatGroq(**kwargs, model_kwargs={"reasoning_format": "hidden"})


def strip_think(text: str) -> str:
    text = _THINK_BLOCK.sub("", text or "")
    close = text.lower().rfind("</think>")
    if close != -1:
        text = text[close + len("</think>") :]
    else:
        text = _UNCLOSED_THINK.sub("", text)
    return text.strip()


def extract_json(text: str) -> dict[str, Any]:
    """Return the first balanced {...} object in `text` that parses as JSON."""
    text = strip_think(text)
    for start in (m.start() for m in re.finditer(r"\{", text)):
        depth, in_string, escaped = 0, False, False
        for end in range(start, len(text)):
            ch = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("No JSON object found in model output.")


def _map_error(exc: Exception) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return LLMAuthError()
    if _too_large(exc):
        return LLMUnavailableError(
            "This request is larger than the Groq plan allows per minute. Lower GROQ_MAX_TOKENS in .env "
            "or ask a shorter question."
        )
    if isinstance(exc, groq.RateLimitError):
        return LLMRateLimitError()
    if isinstance(exc, groq.NotFoundError):
        return LLMUnavailableError(
            f"The configured Groq model is not available for this key. Check GROQ_MODEL in .env "
            f"(currently '{settings.groq_model}')."
        )
    if isinstance(exc, (groq.APITimeoutError, groq.APIConnectionError, groq.InternalServerError)):
        return LLMUnavailableError()
    raise exc


_backoff = wait_exponential(multiplier=1, min=1, max=4)


def _wait(retry_state: RetryCallState) -> float:
    """Honour Groq's retry-after on 429s (free tier is per-minute token limits), else exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, groq.RateLimitError):
        # Groq's retry-after is often a few seconds even when the minute's budget is still spent,
        # so grow the wait each attempt (2, 4, 8, 16s...) and take whichever is longer.
        growing = 2.0 ** retry_state.attempt_number
        try:
            suggested = float(exc.response.headers.get("retry-after", "")) + 0.5
        except ValueError:
            suggested = 0.0
        return min(max(suggested, growing), MAX_RETRY_AFTER_S)
    return _backoff(retry_state)


def _stop(retry_state: RetryCallState) -> bool:
    """3 attempts for timeouts/connection errors; per-minute rate limits get more, within ~60s."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, groq.RateLimitError):
        return retry_state.attempt_number >= RATE_LIMIT_ATTEMPTS or retry_state.seconds_since_start > MAX_RATE_LIMIT_WAIT_S
    return retry_state.attempt_number >= 3


def _too_large(exc: BaseException) -> bool:
    """Groq also uses 429 for a single request that exceeds a per-minute limit; waiting never helps."""
    return isinstance(exc, groq.RateLimitError) and "request too large" in str(exc).lower()


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, _RETRYABLE) and not _too_large(exc)


@retry(
    retry=retry_if_exception(_retryable),
    stop=_stop,
    wait=_wait,
    reraise=True,
)
def _invoke_with_retry(runnable: Any, messages: Sequence[Any]) -> Any:
    return runnable.invoke(messages)


def _invoke(runnable: Any, messages: Sequence[Any]) -> Any:
    try:
        return _invoke_with_retry(runnable, messages)
    except Exception as exc:
        if isinstance(exc, groq.APIStatusError):
            logger.warning("Groq %s after retries: %s", exc.status_code, str(exc)[:400])
        raise _map_error(exc) from exc


def invoke_text(
    messages: Sequence[Any], model: str | None = None, temperature: float = 0.1, hide_reasoning: bool = True
) -> str:
    response = _invoke(get_chat(model, temperature, hide_reasoning), messages)
    return strip_think(str(response.content))


def invoke_json(messages: Sequence[Any], schema: type[T], model: str | None = None) -> T:
    chat = get_chat(model, temperature=0.0)
    try:
        result = _invoke(chat.with_structured_output(schema), messages)
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)
    except (LLMAuthError, LLMRateLimitError):
        raise
    except Exception as exc:
        logger.info("Structured output failed (%s); falling back to JSON parsing.", type(exc).__name__)

    instruction = (
        "Respond with only a JSON object (no prose, no code fences) matching this JSON schema:\n"
        + json.dumps(schema.model_json_schema())
    )
    text = invoke_text([*messages, ("user", instruction)], model=model, temperature=0.0)
    try:
        return schema.model_validate(extract_json(text))
    except (ValueError, ValidationError) as exc:
        raise LLMUnavailableError("The language model returned a response that could not be read.") from exc


def list_models() -> list[str]:
    try:
        response = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {_api_key()}"}, timeout=15)
    except httpx.HTTPError as exc:
        raise LLMUnavailableError("Could not reach Groq. Check your internet connection.") from exc
    if response.status_code in (401, 403):
        raise LLMAuthError()
    if response.status_code == 429:
        raise LLMRateLimitError()
    if response.status_code >= 400:
        raise LLMUnavailableError(f"Groq returned HTTP {response.status_code} when listing models.")
    return sorted(m["id"] for m in response.json().get("data", []))


@functools.cache
def check_models() -> dict[str, Any]:
    status = {"key_ok": False, "chat_model_ok": False, "guard_model_ok": False, "message": ""}
    try:
        models = set(list_models())
    except LLMError as exc:
        status["message"] = exc.user_message
        return status

    status["key_ok"] = True
    status["chat_model_ok"] = settings.groq_model in models
    status["guard_model_ok"] = settings.groq_guard_model in models
    problems = []
    if not status["chat_model_ok"]:
        problems.append(f"Chat model '{settings.groq_model}' is not available; update GROQ_MODEL in .env.")
    if not status["guard_model_ok"]:
        problems.append(
            f"Guard model '{settings.groq_guard_model}' is not available; rule-based moderation will be used."
        )
    status["message"] = " ".join(problems) or "Groq key and models OK."
    return status
