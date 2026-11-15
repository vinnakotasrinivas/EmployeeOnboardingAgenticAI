from __future__ import annotations

from pathlib import PurePath

from app.config import settings
from app.ingestion.models import ValidationResult

ALLOWED = {".pdf": "pdf", ".txt": "txt", ".csv": "csv", ".xlsx": "xlsx", ".xls": "xls"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".svg"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
OFFICE_EXTS = {".docx", ".doc", ".pptx", ".ppt"}
MACRO_EXTS = {".xlsm", ".xltm", ".xlsb"}

MAGIC = {
    "pdf": b"%PDF",
    "xlsx": b"PK\x03\x04",
    "xls": b"\xd0\xcf\x11\xe0",
}
SNIFF = [
    (b"%PDF", "PDF"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG", "PNG"),
    (b"GIF8", "GIF"),
    (b"PK\x03\x04", "ZIP"),
    (b"\xd0\xcf\x11\xe0", "an old Office file"),
    (b"MZ", "a Windows program"),
]
TEXT_SNIFF_BYTES = 64 * 1024


def _fail(code: str, message: str, size: int, file_type: str | None = None) -> ValidationResult:
    return ValidationResult(ok=False, code=code, message=message, file_type=file_type, size_bytes=size)


def _sniff(data: bytes) -> str:
    for magic, label in SNIFF:
        if data.startswith(magic):
            return label
    return "binary data" if b"\x00" in data[:TEXT_SNIFF_BYTES] else "text"


def _is_text(data: bytes) -> bool:
    # Every byte sequence decodes as latin-1, so for text files the NUL check is what matters.
    if any(data.startswith(magic) for magic, _ in SNIFF if len(magic) >= 3):
        return False
    return b"\x00" not in data[:TEXT_SNIFF_BYTES]


def validate_file(filename: str, data: bytes) -> ValidationResult:
    size = len(data)
    ext = PurePath(filename).suffix.lower()

    if size == 0:
        return _fail("empty", "File is empty.", size)
    if size >= settings.max_file_bytes:
        mb = size / (1024 * 1024)
        return _fail(
            "too_large",
            f"File is {mb:.1f} MB. Maximum allowed is under {settings.max_file_mb:g} MB.",
            size,
        )
    if ext in IMAGE_EXTS:
        return _fail(
            "unsupported_image",
            "Images are not supported. Upload text-based documents (PDF, TXT, CSV, Excel).",
            size,
        )
    if ext in ARCHIVE_EXTS:
        return _fail(
            "unsupported_archive",
            "Archives are not supported. Extract the files and upload them individually.",
            size,
        )
    if ext in OFFICE_EXTS:
        return _fail("unsupported_office", "Word/PowerPoint not supported. Export as PDF and re-upload.", size)
    if ext in MACRO_EXTS:
        return _fail(
            "unsupported_macro",
            "Macro-enabled Excel files are not supported. Save as .xlsx and re-upload.",
            size,
        )
    if ext not in ALLOWED:
        shown = f"'{ext}'" if ext else "(no extension)"
        return _fail(
            "unsupported_format",
            f"Unsupported file type {shown}. Allowed: PDF, TXT, CSV, XLSX, XLS.",
            size,
        )

    file_type = ALLOWED[ext]
    if file_type in MAGIC:
        if not data.startswith(MAGIC[file_type]):
            return _fail(
                "type_mismatch",
                f"This file claims to be {file_type.upper()} but its content looks like {_sniff(data)}.",
                size,
                file_type,
            )
    elif not _is_text(data):
        return _fail(
            "type_mismatch",
            f"This file claims to be {file_type.upper()} but its content looks like {_sniff(data)}.",
            size,
            file_type,
        )

    return ValidationResult(ok=True, code="ok", message="", file_type=file_type, size_bytes=size)
