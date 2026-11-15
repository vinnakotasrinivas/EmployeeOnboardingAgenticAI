from __future__ import annotations

import io
import logging
from pathlib import PurePath

import pandas as pd
from pypdf import PdfReader
from pypdf.errors import DependencyError, FileNotDecryptedError

from app.ingestion.models import LoadedDoc, LoadResult

logger = logging.getLogger(__name__)
# pypdf logs a warning for every damaged PDF; load_file already turns those into a user message.
logging.getLogger("pypdf").setLevel(logging.ERROR)

MIN_PDF_TEXT_CHARS = 20
CSV_SHEET = "data"

PDF_CORRUPT = "Could not read this PDF. It may be damaged."
PDF_ENCRYPTED = "This PDF is password-protected. Remove the password and re-upload."
PDF_SCANNED = "No text found. This looks like a scanned PDF; OCR is not supported."
EXCEL_CORRUPT = "Could not read this Excel file. It may be damaged."
NO_TEXT = "No text found in this file."


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _short_reason(exc: Exception) -> str:
    reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return reason if len(reason) <= 120 else reason[:117] + "..."


def to_markdown(df: pd.DataFrame) -> str:
    shown = df.copy()
    for col in shown.columns:
        series = shown[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            has_time = (series.dropna().dt.normalize() != series.dropna()).any()
            shown[col] = series.dt.strftime("%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d")
    return shown.astype(object).where(shown.notna(), "").to_markdown(index=False)


def _table_result(source: str, file_type: str, sheets: dict[str, pd.DataFrame]) -> LoadResult:
    result = LoadResult()
    total_rows = 0
    for sheet, df in sheets.items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        result.tables[f"{source}:{sheet}"] = df
        total_rows += len(df)
        heading = f"# {source}" if file_type == "csv" else f"# {source} - sheet: {sheet}"
        result.docs.append(
            LoadedDoc(
                text=f"{heading}\n\n{to_markdown(df)}",
                metadata={
                    "source": source,
                    "file_type": file_type,
                    "sheet": sheet,
                    "row_start": 1,
                    "row_end": len(df),
                },
            )
        )
    if not result.docs:
        result.error = NO_TEXT
    result.stats = {"rows": total_rows}
    if file_type != "csv":
        result.stats["sheets"] = len(result.tables)
    return result


def _load_pdf(source: str, data: bytes) -> LoadResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    return LoadResult(error=PDF_ENCRYPTED)
            except (DependencyError, FileNotDecryptedError, NotImplementedError):
                return LoadResult(error=PDF_ENCRYPTED)
        pages = [page.extract_text() or "" for page in reader.pages]
    except FileNotDecryptedError:
        return LoadResult(error=PDF_ENCRYPTED)
    except Exception as exc:
        logger.info("PDF %s unreadable: %s", source, exc)
        return LoadResult(error=PDF_CORRUPT)

    if not pages:
        return LoadResult(error=PDF_CORRUPT)
    if sum(len(p.strip()) for p in pages) < MIN_PDF_TEXT_CHARS:
        return LoadResult(error=PDF_SCANNED, stats={"pages": len(pages)})

    docs = [
        LoadedDoc(text=text.strip(), metadata={"source": source, "file_type": "pdf", "page": number})
        for number, text in enumerate(pages, start=1)
        if text.strip()
    ]
    return LoadResult(docs=docs, stats={"pages": len(pages)})


def _load_txt(source: str, data: bytes) -> LoadResult:
    text = _decode_text(data).strip()
    if not text:
        return LoadResult(error=NO_TEXT)
    doc = LoadedDoc(text=text, metadata={"source": source, "file_type": "txt"})
    return LoadResult(docs=[doc], stats={"lines": text.count("\n") + 1})


def _load_csv(source: str, data: bytes) -> LoadResult:
    try:
        df = pd.read_csv(io.StringIO(_decode_text(data)))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        return LoadResult(error=f"Could not parse CSV: {_short_reason(exc)}.")
    return _table_result(source, "csv", {CSV_SHEET: df})


def _load_excel(source: str, data: bytes, file_type: str) -> LoadResult:
    engine = "openpyxl" if file_type == "xlsx" else "xlrd"
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, engine=engine)
    except Exception as exc:
        logger.info("Excel %s unreadable: %s", source, exc)
        return LoadResult(error=EXCEL_CORRUPT)
    return _table_result(source, file_type, sheets)


def load_file(filename: str, data: bytes) -> LoadResult:
    source = PurePath(filename).name
    ext = PurePath(filename).suffix.lower()
    try:
        if ext == ".pdf":
            return _load_pdf(source, data)
        if ext == ".txt":
            return _load_txt(source, data)
        if ext == ".csv":
            return _load_csv(source, data)
        if ext in (".xlsx", ".xls"):
            return _load_excel(source, data, ext[1:])
        return LoadResult(error=f"Unsupported file type '{ext}'.")
    except Exception as exc:
        logger.exception("Unexpected error loading %s", source)
        return LoadResult(error=f"Could not read this file: {_short_reason(exc)}.")
