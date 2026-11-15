from __future__ import annotations

import hashlib
import re
from typing import Any

import numpy as np
import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq

from app.config import settings
from app.guardrails import input_guard, moderation, output_guard
from app.ingestion import relevance
from app.llm import groq_client
from app.llm.errors import LLMUnavailableError
from app.store import embeddings as embeddings_module
from app.store import tables, vector_store

FAKE_DIM = 384


def pytest_collection_modifyitems(items):
    for item in items:
        if "real_embeddings" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.slow)


@pytest.fixture(autouse=True)
def offline_llm(request, monkeypatch):
    """Offline tests can never reach Groq: any real chat call fails like an outage, and moderation is stubbed.
    Tests that exercise moderation or the client patch below this."""
    if request.node.get_closest_marker("live"):
        return

    def blocked(*args, **kwargs):
        raise LLMUnavailableError("Offline test tried to call Groq.")

    monkeypatch.setattr(ChatGroq, "_generate", blocked)
    monkeypatch.setattr(input_guard, "moderate", lambda text, role="user": (True, []))
    monkeypatch.setattr(output_guard, "moderate", lambda text, role="user": (True, []))
    moderation.moderate.cache_clear()


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """Registry, FAISS index and uploads live in tmp_path; in-memory stores start empty."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    vector_store.reset()
    tables.reset()
    yield tmp_path
    vector_store.reset()
    tables.reset()


class HashEmbeddings(Embeddings):
    """Deterministic bag-of-words vectors: texts sharing words are similar. Fast and offline."""

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(FAKE_DIM, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % FAKE_DIM] += 1.0
        norm = np.linalg.norm(vec)
        return (vec / norm if norm else vec).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture
def fake_embeddings(monkeypatch):
    fake = HashEmbeddings()
    for module in (embeddings_module, vector_store):
        monkeypatch.setattr(module, "get_embeddings", lambda: fake)
    relevance.category_vectors.cache_clear()
    vector_store.reset()
    yield fake
    relevance.category_vectors.cache_clear()  # don't leak fake topic vectors into later tests
    vector_store.reset()


@pytest.fixture(scope="session")
def real_embeddings():
    """The real bge model, loaded once. Tests using this are marked `slow` automatically."""
    model = embeddings_module.get_embeddings()
    model.embed_query("warm up")
    return model


class FakeChat:
    """Stands in for ChatGroq: no tool calling, so invoke_json takes its text + JSON-extraction path."""

    def __init__(self, replies: list[str], prompts: list[Any]):
        self.replies, self.prompts = replies, prompts

    def with_structured_output(self, schema):
        raise NotImplementedError("tool calling not supported")

    def invoke(self, messages):
        self.prompts.append(messages)
        return AIMessage(content=self.replies.pop(0) if len(self.replies) > 1 else self.replies[0])


class MockLLM:
    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self._mp = monkeypatch
        self.calls: list[str] = []
        self.prompts: list[Any] = []

    def reply(self, module: Any, name: str, *replies: Any) -> None:
        """Make `module.name` (e.g. reasoner.invoke_text) return `replies` in order, repeating the last one.
        Exceptions are raised instead of returned."""
        queue = list(replies)
        label = f"{module.__name__.rsplit('.', 1)[-1]}.{name}"

        def fake(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(label)
            item = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(item, BaseException):
                raise item
            return item

        self._mp.setattr(module, name, fake)

    def chat(self, *replies: str) -> None:
        """Replace the Groq chat model itself, so the real invoke_text/invoke_json parsing runs on `replies`."""
        self._mp.setattr(settings, "groq_api_key", "test-key")
        self._mp.setattr(groq_client, "get_chat", lambda *a, **k: FakeChat(list(replies), self.prompts))

    def count(self, label: str) -> int:
        return self.calls.count(label)


@pytest.fixture
def mock_llm(monkeypatch) -> MockLLM:
    return MockLLM(monkeypatch)
