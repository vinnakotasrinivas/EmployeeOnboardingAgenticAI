from __future__ import annotations

import functools
import os

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from langchain_huggingface import HuggingFaceEmbeddings  # noqa: E402

from app.config import settings  # noqa: E402

# bge-*-v1.5 models retrieve better when short queries (not passages) carry this instruction.
BGE_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "


@functools.cache
def get_embeddings() -> HuggingFaceEmbeddings:
    query_kwargs: dict = {"normalize_embeddings": True}
    if "bge" in settings.embedding_model.lower():
        query_kwargs["prompt"] = BGE_QUERY_PROMPT
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
        query_encode_kwargs=query_kwargs,
    )


def embed_texts(texts: list[str]) -> np.ndarray:
    return np.asarray(get_embeddings().embed_documents(texts), dtype=np.float32)
