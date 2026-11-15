# Step 14b: ARCHITECTURE.md

## Spec

**Goal:** a reviewer can understand how OnboardIQ works, and why it was built this way, without reading the code.

**Files created or changed**
- `ARCHITECTURE.md` in the project root, next to `README.md`
- `README.md`: make sure it links to `ARCHITECTURE.md`

**`ARCHITECTURE.md` sections**
- System diagram: the Mermaid diagram from the master plan.
- Ingestion flow: validation order, relevance thresholds, chunking strategy.
- Agent roles: a table with agent, input, output, LLM or not, and failure behaviour.
- Retrieval and RAG: embeddings, FAISS, thresholds, citation format.
- Safety: input and output guards, the guard model and its rule-based fallback, the validator loop, PII handling, error handling.
- Design decisions and trade-offs: why FAISS over Chroma, why bge-small, why Groq, why a relevance gate.
- Challenges faced and how you solved them. Fill this in honestly from your build notes; the agent can draft it from git history.
- Limitations and future work: OCR, multi-language support, auth, multi-tenant storage, streaming answers.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md and docs/build_guide/14b_architecture.md for the exact spec. This is STEP 14b ONLY: ARCHITECTURE.md in the project root (same folder as README.md).
Write ARCHITECTURE.md with all sections from the spec. Take the numbers (thresholds, chunk sizes, token budgets, retry limits, model names) from the code and app/config.py, not from the plan, wherever they differ. For "Challenges faced", draft from `git log --oneline` (if there is history) and the code, and mark it clearly with "TODO: review and personalise" so I edit it.

Make sure README.md links to ARCHITECTURE.md. When done, list every file path ARCHITECTURE.md mentions and confirm each one exists.
```

## Checkpoint

```powershell
Test-Path ARCHITECTURE.md
Select-String -Path README.md -Pattern "ARCHITECTURE.md"
```

Open `ARCHITECTURE.md` in Cursor's Markdown preview (Ctrl+Shift+V) and check:
- [ ] The Mermaid diagram renders.
- [ ] The agent table covers the input guard, planner, retriever, data analyst, reasoner, validator and output guard.
- [ ] The thresholds match `app/config.py` (for example `RELEVANCE_THRESHOLD`, `SIMILARITY_THRESHOLD`, `TOP_K`).
- [ ] "Challenges faced" is marked "TODO: review and personalise".

**Expected output:** both commands find the file and the link.

## Common problems

- **The Mermaid diagram doesn't render:** node labels with spaces or brackets must be quoted, for example `A["Input guard"]`.
- **Numbers don't match the code:** values changed during the build (for example the off-topic thresholds in step 9 and `GROQ_MAX_TOKENS` in step 11). Always read them from the code.
- **"Challenges faced" reads like generic filler:** replace the draft with what actually went wrong for you; reviewers ask about it.
