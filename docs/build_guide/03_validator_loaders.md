# Step 3: File validator and loaders

## Spec

**Goal:** accept only supported, healthy files with a clear message for everything else, and turn good files into text documents with metadata.

**Files created**
- `app/ingestion/models.py`: shared data types:
  - `ValidationResult(ok: bool, code: str, message: str, file_type: str | None, size_bytes: int)`
  - `LoadedDoc(text: str, metadata: dict)`, where metadata holds `source`, `file_type`, `page` or `row_start`/`row_end`, and `sheet`
  - `LoadResult(docs: list[LoadedDoc], tables: dict[str, DataFrame], stats: dict, error: str | None)`
- `app/ingestion/validator.py`: `validate_file(filename: str, data: bytes) -> ValidationResult`
- `app/ingestion/loaders.py`: `load_file(filename: str, data: bytes) -> LoadResult`
- `tests/test_validator.py`, `tests/test_loaders.py`

**Validation order** (cheap checks first, and no LLM calls). Each failure has an error code and an exact message:

| Check | Code | Message (example) |
| --- | --- | --- |
| 0 bytes | `empty` | "File is empty." |
| size >= 19 MB | `too_large` | "File is 20.0 MB. Maximum allowed is under 19 MB." |
| image extension | `unsupported_image` | "Images are not supported. Upload text-based documents (PDF, TXT, CSV, Excel)." |
| archive extension | `unsupported_archive` | "Archives are not supported. Extract the files and upload them individually." |
| `.docx` / `.pptx` / `.doc` / `.ppt` | `unsupported_office` | "Word/PowerPoint not supported. Export as PDF and re-upload." |
| `.xlsm` | `unsupported_macro` | "Macro-enabled Excel files are not supported. Save as .xlsx and re-upload." |
| any other extension | `unsupported_format` | "Unsupported file type '.exe'. Allowed: PDF, TXT, CSV, XLSX, XLS." |
| magic bytes don't match the extension | `type_mismatch` | "This file claims to be PDF but its content looks like JPEG." |

Magic bytes to check: PDF starts with `%PDF`, XLSX starts with `PK\x03\x04`, XLS starts with `D0 CF 11 E0`, JPEG with `FF D8 FF`, PNG with `89 50 4E 47`. TXT and CSV are fine if they decode as UTF-8 or latin-1 and contain no NUL bytes.

**Loader errors**, returned in `LoadResult.error`:
- **Corrupt PDF:** "Could not read this PDF. It may be damaged."
- **Encrypted PDF:** "This PDF is password-protected. Remove the password and re-upload."
- **Scanned PDF** (fewer than 20 characters of text): "No text found. This looks like a scanned PDF; OCR is not supported."
- **Malformed CSV:** "Could not parse CSV: <short reason>."
- **Non-UTF-8 TXT:** retry with latin-1 before giving up.

**Loader output**
- **PDF:** one `LoadedDoc` per page, with `page` metadata.
- **TXT:** one `LoadedDoc` for the whole file.
- **CSV and XLSX:** keep the full DataFrame in `tables[f"{source}:{sheet}"]` for the Data Analyst agent in step 8. Also produce row-group text docs later in chunking. For now, one `LoadedDoc` per sheet containing the headers plus all rows as markdown is enough.
- **Stats:** `pages`, `rows` and `sheets`, depending on the file type.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "1. Document reading and validation") for context, and docs/build_guide/03_validator_loaders.md for the exact spec. This is STEP 3 ONLY: validator and loaders. No relevance, chunking, or LLM code.

Add dependencies: `uv add pypdf tabulate xlrd` and `uv add --dev pytest`.

Implement exactly what the spec file describes:
- app/ingestion/models.py with ValidationResult, LoadedDoc, LoadResult (dataclasses or pydantic).
- app/ingestion/validator.py with validate_file(filename, data) -> ValidationResult, using the check order, codes, and messages from the spec table. Use settings.max_file_bytes from app/config.py. Size check uses >= (19 MB exactly is rejected). Format the size with one decimal.
- app/ingestion/loaders.py with load_file(filename, data) -> LoadResult. Never raise to the caller; convert errors into LoadResult.error with the friendly messages from the spec.
- tests/test_validator.py: one test per file in docs/sample_data/invalid/ (skip oversize.pdf if missing), plus a parametrized test that every file in docs/sample_data/{pdf,txt,csv,xlsx}/ and docs/sample_data/irrelevant/ is valid.
- tests/test_loaders.py: pdf/employee_handbook.pdf yields 3 pages; csv/team_directory.csv yields 184 rows and a DataFrame in tables; xlsx/training_schedule.xlsx yields 3 sheets (Course Catalog, Session Schedule, New Hire Assignments); invalid/corrupt.pdf returns an error, not an exception.

Run `uv run pytest -q` and show the result. Fix failures before finishing.
```

## Checkpoint

```powershell
uv run pytest -q
uv run python -c "from app.ingestion.validator import validate_file; from pathlib import Path; [print(p.name, '->', validate_file(p.name, p.read_bytes()).message or 'OK') for p in Path('docs/sample_data/invalid').iterdir()]"
```

**Expected output:** all tests pass, and each invalid file prints its own message (not one generic error). The exception is `corrupt.pdf`, which prints `OK`: its header is a real `%PDF`, so the validator accepts it, and the loader rejects it with "Could not read this PDF. It may be damaged."

## Common problems

- **`fake_pdf.pdf` passes validation:** the magic-byte check must run after the extension check and must read the first bytes of `data`, not the filename.
- **pypdf prints warnings for `corrupt.pdf`:** that's fine, as long as `load_file` returns an error instead of raising.
- **`.xls` loading fails:** `xlrd` is needed for old `.xls` files. pandas uses `openpyxl` for `.xlsx`.
