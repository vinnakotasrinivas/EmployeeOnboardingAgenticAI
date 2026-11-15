from pathlib import Path

import pytest

from app.config import PROJECT_ROOT
from app.ingestion.validator import validate_file

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
INVALID = SAMPLES / "invalid"
VALID_FILES = sorted(
    p for folder in ("pdf", "txt", "csv", "xlsx", "irrelevant") for p in (SAMPLES / folder).iterdir()
)


def check(path: Path):
    return validate_file(path.name, path.read_bytes())


@pytest.mark.parametrize("path", VALID_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_sample_files_are_valid(path):
    result = check(path)
    assert result.ok, result.message
    assert result.code == "ok"
    assert result.file_type == path.suffix[1:]


def test_empty():
    result = check(INVALID / "empty.txt")
    assert (result.ok, result.code, result.message) == (False, "empty", "File is empty.")


def test_oversize():
    path = INVALID / "oversize.pdf"
    if not path.exists():
        pytest.skip("run scripts/make_test_files.py --oversize to create oversize.pdf")
    result = check(path)
    assert result.code == "too_large"
    assert result.message == "File is 20.0 MB. Maximum allowed is under 19 MB."


def test_exactly_19_mb_is_rejected():
    result = validate_file("big.pdf", b"%PDF" + b"0" * (19 * 1024 * 1024 - 4))
    assert result.code == "too_large"


def test_just_under_19_mb_is_accepted():
    result = validate_file("big.pdf", b"%PDF" + b"0" * (19 * 1024 * 1024 - 5))
    assert result.ok


def test_image():
    result = check(INVALID / "photo.jpg")
    assert result.code == "unsupported_image"
    assert result.message.startswith("Images are not supported.")


def test_archive():
    result = check(INVALID / "archive.zip")
    assert result.code == "unsupported_archive"
    assert "Extract the files" in result.message


def test_powerpoint():
    result = check(INVALID / "slides.pptx")
    assert result.code == "unsupported_office"
    assert result.message == "Word/PowerPoint not supported. Export as PDF and re-upload."


def test_macro_excel():
    result = check(INVALID / "macro_book.xlsm")
    assert result.code == "unsupported_macro"
    assert "Save as .xlsx" in result.message


def test_spoofed_pdf():
    result = check(INVALID / "fake_pdf.pdf")
    assert result.code == "type_mismatch"
    assert result.message == "This file claims to be PDF but its content looks like JPEG."


def test_corrupt_pdf_passes_validation():
    # Header is a real %PDF; the damage is only found by the loader.
    assert check(INVALID / "corrupt.pdf").ok


def test_every_invalid_file_has_its_own_message():
    files = [p for p in INVALID.iterdir() if p.name != "corrupt.pdf"]
    results = [check(p) for p in files]
    assert all(not r.ok for r in results)
    assert len({r.code for r in results}) == len(results)


@pytest.mark.parametrize(
    ("filename", "data", "code"),
    [
        ("tool.exe", b"MZ\x90\x00", "unsupported_format"),
        ("notes", b"hello", "unsupported_format"),
        ("letter.docx", b"PK\x03\x04", "unsupported_office"),
        ("PHOTO.PNG", b"\x89PNG", "unsupported_image"),
        ("table.xlsx", b"%PDF-1.4", "type_mismatch"),
        ("old.xls", b"PK\x03\x04", "type_mismatch"),
        ("notes.txt", b"\x89PNG\r\n\x1a\n\x00\x00", "type_mismatch"),
        ("data.csv", b"a,b\x00\x00", "type_mismatch"),
    ],
)
def test_synthetic_cases(filename, data, code):
    assert validate_file(filename, data).code == code


def test_unsupported_format_message():
    assert validate_file("tool.exe", b"MZ").message == "Unsupported file type '.exe'. Allowed: PDF, TXT, CSV, XLSX, XLS."


def test_latin1_text_is_valid():
    assert validate_file("notes.txt", "Café résumé".encode("latin-1")).ok
