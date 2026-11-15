# Step 6: Chunking, embeddings and FAISS

## Spec

**Goal:** split loaded documents into chunks, embed them locally with Hugging Face, store them in a FAISS index on disk, and search them by similarity.

**Files created**
- `app/ingestion/chunker.py`
- `app/store/embeddings.py`
- `app/store/vector_store.py`
- `scripts/check_search.py`
- `tests/test_chunker.py`, `tests/test_vector_store.py`
- Also updates `classify_by_embedding` in `app/ingestion/relevance.py` (the TODO from step 5).

**Chunker**
- **Prose (PDF and TXT):** use `RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=700, chunk_overlap=100)`. Page metadata stays on each chunk.
- **Tables (CSV and Excel):** groups of 25 rows. Each chunk text starts with `Source: <file>, sheet <sheet>, rows <a>-<b>` followed by the header row and the rows as markdown. Metadata includes `row_start` and `row_end`.
- **Every chunk gets** `doc_id`, `source`, `category`, `file_type`, `chunk_id` (`f"{doc_id}:{n}"`), and `page` or row metadata.
- `chunk(load_result, doc_id, category) -> list[langchain Document]`

**Embeddings**
- `get_embeddings()` is cached and returns `HuggingFaceEmbeddings(model_name=settings.embedding_model, encode_kwargs={"normalize_embeddings": True})` on CPU.
- `embed_texts(list[str]) -> np.ndarray` is a helper used by the relevance fallback.

**Vector store (one module-level singleton, protected by a `threading.Lock`)**
- `load_or_create()` loads from `settings.faiss_dir` if it exists. Use `distance_strategy=MAX_INNER_PRODUCT` so scores are cosine similarity.
- `add_documents(docs) -> int` adds the chunks and saves to disk.
- `delete_doc(doc_id) -> int` removes all chunks whose `doc_id` matches (by docstore ids) and saves.
- `search(query, k=settings.top_k, category=None, threshold=settings.similarity_threshold) -> list[(Document, score)]` keeps results with score >= threshold, sorted by score descending.
- `stats() -> {"chunks": int, "docs": int}`
- `rebuild_from_registry()`: if the index fails to load, delete it, re-index every `indexed` registry entry from `uploads_dir`, and log a warning.
- When a document reaches `indexed`, save its raw file under `uploads_dir` so rebuilds are possible. (Step 5 only saved pending files; extend it to all indexed files.)

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "3. RAG") and docs/build_guide/06_chunk_embed_faiss.md for the exact spec. This is STEP 6 ONLY: chunking, embeddings, FAISS store. No agents yet.

Add dependencies: `uv add langchain-community langchain-text-splitters langchain-huggingface sentence-transformers faiss-cpu tiktoken numpy`.
If torch installs a huge CUDA build on Windows, configure the CPU-only index for torch in pyproject.toml (https://download.pytorch.org/whl/cpu) via [tool.uv.sources] and [[tool.uv.index]].

Implement app/ingestion/chunker.py, app/store/embeddings.py, app/store/vector_store.py exactly as specified. FAISS must use normalized embeddings with MAX_INNER_PRODUCT so scores are cosine similarity in [0,1]-ish range. Use allow_dangerous_deserialization=True only when loading our own index from settings.faiss_dir.

Replace the keyword stub in app/ingestion/relevance.py classify_by_embedding with real embedding similarity against the category descriptions (pick best category; relevant if best score >= 0.45; confidence = score). Keep the "fallback:" reason prefix.

Create scripts/check_search.py: index all files in docs/sample_data/{pdf,txt,csv,xlsx}/ (validate, load, chunk with category from the relevance gate or "unknown"), then run 4 queries ("How many PTO days do US employees get?", "Who is Siddharth Patel's manager?", "What happens on day 1 of onboarding?", "How do I connect to the VPN?") and print top-5 results with score, source, page/rows, and the first 100 chars. Accept a --reset flag that deletes data/faiss_index first.

Add tests: chunker (prose chunk sizes, table chunks have headers and row ranges, metadata present) and vector store (use a tmp faiss dir; add, search returns the right doc, delete_doc removes it, threshold filters out an unrelated query like "pasta carbonara recipe").

Run pytest and the check script with --reset, and show the outputs.
```

## Checkpoint

```powershell
uv run python scripts/check_search.py --reset
uv run pytest -q
```

**Expected output:** the PTO query's top result comes from `employee_handbook.pdf`, day 1 from `onboarding_checklist.csv`, `first_week_faq.txt` or the handbook, and the VPN query from `how_to_guides.txt` or `it_security_policy.pdf`. For the manager query, a `team_directory.csv` chunk appears in the top 5 but may not rank first: Siddharth Patel also appears in `training_schedule.xlsx`, and embeddings are weak at exact name lookups. The Data Analyst agent in step 8 does those lookups with pandas. Top scores should be roughly 0.5 to 0.85.

## Common problems

- **`uv add` takes forever or downloads 2 GB:** that's the CUDA build of torch. Use the CPU-only index from the prompt.
- **All scores are around 0.8 even for nonsense queries:** bge models score everything fairly high. Raise `SIMILARITY_THRESHOLD` in `.env` (try 0.45) and check that an irrelevant query returns nothing.
- **Hugging Face symlink warning on Windows:** harmless. Set `HF_HUB_DISABLE_SYMLINKS_WARNING=1` in `.env` to hide it.
- **`delete_doc` leaves chunks behind:** the docstore ids have to be tracked per `doc_id`. Ask the agent to look them up from `index_to_docstore_id` and the stored metadata.
