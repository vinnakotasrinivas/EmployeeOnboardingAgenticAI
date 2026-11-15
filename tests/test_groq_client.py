import groq
import httpx
import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.llm import groq_client
from app.llm.errors import LLMAuthError, LLMRateLimitError, LLMUnavailableError
from app.llm.groq_client import extract_json, invoke_json, invoke_text, strip_think


class Answer(BaseModel):
    answer: str
    confidence: float


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>let me reason</think>\nOK", "OK"),
        ("<think>still thinking and never closed", ""),
        ("  OK  ", "OK"),
        ("<THINK>a</THINK>Hello <think>b</think>world", "Hello world"),
        ("partial reasoning without opening tag</think>Final", "Final"),
    ],
)
def test_strip_think(raw, expected):
    assert strip_think(raw) == expected


def test_extract_json_from_prose():
    text = '<think>{"draft": 1}</think>Sure! Here it is: {"answer": "Paris", "confidence": 0.9} Hope that helps.'
    assert extract_json(text) == {"answer": "Paris", "confidence": 0.9}


def test_extract_json_with_braces_in_strings_and_fences():
    text = '```json\n{"answer": "use {curly} braces", "confidence": 1}\n```'
    assert extract_json(text)["answer"] == "use {curly} braces"


def test_extract_json_skips_invalid_candidates():
    assert extract_json('{not json} then {"a": 1}') == {"a": 1}


def test_extract_json_raises_without_object():
    with pytest.raises(ValueError):
        extract_json("no json here")


class FakeChat:
    def __init__(self, reply: str, structured_error: Exception | None = None):
        self.reply = reply
        self.structured_error = structured_error

    def with_structured_output(self, schema):
        chat = self

        class Structured:
            def invoke(self, messages):
                raise chat.structured_error or RuntimeError("tool calling not supported")

        return Structured()

    def invoke(self, messages):
        return AIMessage(content=self.reply)


def _groq_error(cls, status):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


def test_invoke_json_falls_back_to_regex(monkeypatch):
    fake = FakeChat('<think>hmm</think>{"answer": "Paris", "confidence": 0.95}')
    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: fake)
    result = invoke_json([("user", "capital of France?")], Answer)
    assert result == Answer(answer="Paris", confidence=0.95)


def test_invoke_text_strips_think(monkeypatch):
    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: FakeChat("<think>x</think> OK"))
    assert invoke_text([("user", "hi")]) == "OK"


def test_auth_error_is_not_retried(monkeypatch):
    calls = []

    class Failing(FakeChat):
        def invoke(self, messages):
            calls.append(1)
            raise _groq_error(groq.AuthenticationError, 401)

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: Failing(""))
    with pytest.raises(LLMAuthError):
        invoke_text([("user", "hi")])
    assert len(calls) == 1


def test_rate_limit_is_retried_then_mapped(monkeypatch):
    calls = []

    class Limited(FakeChat):
        def invoke(self, messages):
            calls.append(1)
            raise _groq_error(groq.RateLimitError, 429)

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: Limited(""))
    monkeypatch.setattr(groq_client._invoke_with_retry.retry, "sleep", lambda s: None)
    with pytest.raises(LLMRateLimitError):
        invoke_text([("user", "hi")])
    assert len(calls) == groq_client.RATE_LIMIT_ATTEMPTS


def test_connection_error_gets_three_attempts(monkeypatch):
    calls = []

    class Offline(FakeChat):
        def invoke(self, messages):
            calls.append(1)
            raise groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: Offline(""))
    monkeypatch.setattr(groq_client._invoke_with_retry.retry, "sleep", lambda s: None)
    with pytest.raises(LLMUnavailableError):
        invoke_text([("user", "hi")])
    assert len(calls) == 3


def test_rate_limit_waits_for_retry_after(monkeypatch):
    waits = []
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    limited = groq.RateLimitError(
        "slow down", response=httpx.Response(429, request=request, headers={"retry-after": "4"}), body=None
    )

    class LimitedOnce(FakeChat):
        def invoke(self, messages):
            if not waits:
                raise limited
            return AIMessage(content="OK")

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: LimitedOnce(""))
    monkeypatch.setattr(groq_client._invoke_with_retry.retry, "sleep", waits.append)
    assert invoke_text([("user", "hi")]) == "OK"
    assert waits == [4.5]


def test_request_too_large_is_not_retried(monkeypatch):
    calls = []
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    too_large = groq.RateLimitError(
        "Request too large for model on output tokens per minute (OTPM): Limit 1000, Requested 2048",
        response=httpx.Response(429, request=request), body=None,
    )

    class TooLarge(FakeChat):
        def invoke(self, messages):
            calls.append(1)
            raise too_large

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: TooLarge(""))
    with pytest.raises(LLMUnavailableError, match="GROQ_MAX_TOKENS"):
        invoke_text([("user", "hi")])
    assert len(calls) == 1


def test_rate_limit_waits_grow_each_attempt(monkeypatch):
    waits = []

    class LimitedTwice(FakeChat):
        def invoke(self, messages):
            if len(waits) < 3:
                raise _groq_error(groq.RateLimitError, 429)
            return AIMessage(content="OK")

    monkeypatch.setattr(groq_client, "get_chat", lambda *a, **k: LimitedTwice(""))
    monkeypatch.setattr(groq_client._invoke_with_retry.retry, "sleep", waits.append)
    assert invoke_text([("user", "hi")]) == "OK"
    assert waits == [2.0, 4.0, 8.0]


def test_get_chat_caps_output_tokens(monkeypatch):
    monkeypatch.setattr(groq_client.settings, "groq_api_key", "test-key")
    assert groq_client.get_chat().max_tokens == groq_client.settings.groq_max_tokens


def test_missing_key_raises_auth_error(monkeypatch):
    monkeypatch.setattr(groq_client.settings, "groq_api_key", "")
    with pytest.raises(LLMAuthError):
        groq_client.get_chat()
