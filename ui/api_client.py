"""Thin HTTP client for the OnboardIQ API. The UI talks to the backend only through this module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_API_URL = "http://127.0.0.1:8766"
TIMEOUT_S = 120.0
ASK_TIMEOUT_S = 240.0  # several agent calls, each of which may wait out a Groq rate limit
UPLOAD_TIMEOUT_S = 600.0  # each file may need an LLM relevance call, and Groq rate limits add waits
START_API = "uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8766 --reload --reload-dir app"


class APIError(Exception):
    """A request failed. `message` is safe to show to the user."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class APIUnavailableError(APIError):
    pass


def api_url() -> str:
    return (os.getenv("API_URL") or DEFAULT_API_URL).rstrip("/")


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"The API returned an error ({response.status_code})."
    if isinstance(body, dict):
        if isinstance(body.get("error"), str):
            return body["error"]
        if isinstance(body.get("detail"), list) and body["detail"]:
            return str(body["detail"][0].get("msg", body["detail"][0]))
    return f"The API returned an error ({response.status_code})."


def _request(method: str, path: str, timeout: float = TIMEOUT_S, **kwargs: Any) -> Any:
    url = f"{api_url()}{path}"
    try:
        response = httpx.request(method, url, timeout=timeout, **kwargs)
    except httpx.TimeoutException:
        raise APIError("The API took too long to respond. Try again in a moment.") from None
    except httpx.HTTPError:
        raise APIUnavailableError(f"The OnboardIQ API is not running at {api_url()}.") from None
    if response.is_error:
        raise APIError(_error_message(response), response.status_code)
    return response.json()


def health() -> dict[str, Any]:
    return _request("GET", "/health", timeout=10)


def documents() -> list[dict[str, Any]]:
    return _request("GET", "/documents", timeout=10)


def upload(files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    payload = [("files", (name, data, "application/octet-stream")) for name, data in files]
    return _request("POST", "/upload", timeout=UPLOAD_TIMEOUT_S, files=payload)


def preview(doc_id: str) -> dict[str, Any]:
    return _request("GET", f"/documents/{doc_id}/preview", timeout=30)


def delete(doc_id: str) -> dict[str, Any]:
    return _request("DELETE", f"/documents/{doc_id}")


def confirm(doc_id: str) -> dict[str, Any]:
    return _request("POST", f"/documents/{doc_id}/confirm", timeout=UPLOAD_TIMEOUT_S)


def discard(doc_id: str) -> dict[str, Any]:
    return _request("POST", f"/documents/{doc_id}/discard")


def ask(question: str) -> dict[str, Any]:
    return _request("POST", "/ask", json={"question": question}, timeout=ASK_TIMEOUT_S)
