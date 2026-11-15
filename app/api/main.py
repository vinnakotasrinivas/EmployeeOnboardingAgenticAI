from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.graph import answer_question
from app.api.schemas import (
    AskRequest,
    AskResponse,
    DeleteResponse,
    DiscardResponse,
    Document,
    Health,
    IngestResult,
)
from app.config import settings
from app.ingestion import pipeline, registry
from app.ingestion.relevance import category_vectors
from app.llm.errors import LLMError
from app.llm.groq_client import check_models
from app.logging_setup import request_id, setup_logging
from app.store import tables, vector_store
from app.store.embeddings import get_embeddings

logger = logging.getLogger("onboardiq.api")

UNEXPECTED = "Something went wrong. Please try again."
MAX_FILES_PER_UPLOAD = 20
LLM_ERROR_STATUS = {"rate_limit": 503, "llm_unavailable": 503, "auth": 503, "unexpected": 500}


def _warm_up() -> None:
    """Load models and indexes once so the first request is fast. Never raises."""
    steps = [
        ("embedding model", lambda: get_embeddings().embed_query("warm up")),
        ("FAISS index", vector_store.load_or_create),
        ("tables", tables.all_tables),
        ("topic vectors", category_vectors),
        ("Groq models", check_models),
    ]
    for name, step in steps:
        start = time.perf_counter()
        try:
            step()
            logger.info("Startup: %s ready in %.1fs", name, time.perf_counter() - start)
        except Exception:
            logger.exception("Startup: %s failed; continuing", name)
    status = check_models()
    if not status.get("key_ok"):
        logger.warning("Groq is not usable: %s", status.get("message"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    _warm_up()
    logger.info("OnboardIQ API ready: %s", vector_store.stats())
    yield


app = FastAPI(
    title="OnboardIQ API",
    description="Upload onboarding documents and ask questions about them.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8765", "http://127.0.0.1:8765"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id.set(rid)
    start = time.perf_counter()
    try:
        if request.url.path == "/upload":
            length = int(request.headers.get("content-length") or 0)
            if length > settings.max_file_bytes * MAX_FILES_PER_UPLOAD:
                return _upload_too_large(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        logger.info("%s %s -> %s in %dms", request.method, request.url.path, response.status_code,
                    (time.perf_counter() - start) * 1000)
        return response
    finally:
        request_id.reset(token)


def _upload_too_large(rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"error": f"Upload too large. Each file must be under {settings.max_file_mb:g} MB."},
        headers={"X-Request-ID": rid},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    logger.warning("LLM error: %s", exc.user_message)
    return JSONResponse(status_code=503, content={"error": exc.user_message})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": UNEXPECTED})


@app.get("/health", response_model=Health)
def health() -> Health:
    groq_status = check_models()
    stats = vector_store.stats()
    return Health(
        status="ok" if groq_status.get("key_ok") and groq_status.get("chat_model_ok") else "degraded",
        groq=groq_status,
        chat_model=settings.groq_model,
        guard_model=settings.groq_guard_model,
        embedding_model=settings.embedding_model,
        chunks=stats["chunks"],
        docs=stats["docs"],
    )


@app.post("/upload", response_model=list[IngestResult])
def upload(request: Request, files: list[UploadFile] = File(...)) -> list[IngestResult]:
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=413, detail=f"Upload at most {MAX_FILES_PER_UPLOAD} files at a time.")
    length = int(request.headers.get("content-length") or 0)
    if length > settings.max_file_bytes * len(files):
        return _upload_too_large(request_id.get())  # type: ignore[return-value]
    batch = [(f.filename or "unnamed", f.file.read()) for f in files]
    results = pipeline.ingest_many(batch)
    logger.info("Upload: %s", ", ".join(f"{r.filename}={r.status}" for r in results))
    return results


@app.get("/documents", response_model=list[Document])
def documents() -> list[dict]:
    return registry.list_documents()


def _get_or_404(doc_id: str) -> dict:
    doc = registry.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@app.get("/documents/{doc_id}/preview", response_model=IngestResult)
def preview_document(doc_id: str) -> IngestResult:
    preview = pipeline.preview_document(doc_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return preview


@app.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str) -> DeleteResponse:
    doc = _get_or_404(doc_id)
    pipeline.delete_document(doc_id)
    return DeleteResponse(deleted=True, chunks_removed=doc["chunks"] if doc["status"] == "indexed" else 0)


@app.post("/documents/{doc_id}/confirm", response_model=IngestResult)
def confirm_document(doc_id: str) -> IngestResult:
    _get_or_404(doc_id)
    return pipeline.confirm_pending(doc_id)


@app.post("/documents/{doc_id}/discard", response_model=DiscardResponse)
def discard_document(doc_id: str) -> DiscardResponse:
    doc = _get_or_404(doc_id)
    if doc["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only documents waiting for review can be discarded.")
    return DiscardResponse(discarded=pipeline.discard_pending(doc_id))


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    start = time.perf_counter()
    result = answer_question(body.question)
    latency_ms = int((time.perf_counter() - start) * 1000)
    if result.get("error"):
        return JSONResponse(status_code=LLM_ERROR_STATUS.get(result["error"], 500), content={"error": result["answer"]})
    return AskResponse(**{k: result[k] for k in ("answer", "confidence", "refused", "citations", "trace")},
                       latency_ms=latency_ms)
