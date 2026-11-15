import io

import pytest
from pypdf import PdfWriter

from app.config import PROJECT_ROOT
from app.ingestion.loaders import load_file

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"


def load(relative: str):
    path = SAMPLES / relative
    return load_file(path.name, path.read_bytes())


def test_pdf_one_doc_per_page():
    result = load("pdf/employee_handbook.pdf")
    assert result.error is None
    assert result.stats == {"pages": 3}
    assert [d.metadata["page"] for d in result.docs] == [1, 2, 3]
    assert all(d.metadata["source"] == "employee_handbook.pdf" for d in result.docs)
    assert "PTO" in " ".join(d.text for d in result.docs)


def test_txt_single_doc():
    result = load("txt/first_week_faq.txt")
    assert result.error is None
    assert len(result.docs) == 1
    assert result.docs[0].metadata == {"source": "first_week_faq.txt", "file_type": "txt"}


def test_csv_rows_and_table():
    result = load("csv/team_directory.csv")
    assert result.error is None
    assert result.stats["rows"] == 184
    table = result.tables["team_directory.csv:data"]
    assert len(table) == 184
    assert "onboarding_buddy_name" in table.columns
    assert result.docs[0].metadata["row_end"] == 184
    assert "Siddharth" in result.docs[0].text


def test_xlsx_sheets():
    result = load("xlsx/training_schedule.xlsx")
    assert result.error is None
    assert result.stats["sheets"] == 3
    assert [d.metadata["sheet"] for d in result.docs] == [
        "Course Catalog",
        "Session Schedule",
        "New Hire Assignments",
    ]
    assert set(result.tables) == {
        "training_schedule.xlsx:Course Catalog",
        "training_schedule.xlsx:Session Schedule",
        "training_schedule.xlsx:New Hire Assignments",
    }
    assert "00:00:00" not in result.docs[1].text


@pytest.mark.parametrize(
    "relative",
    [p.relative_to(SAMPLES).as_posix() for d in ("pdf", "txt", "csv", "xlsx") for p in sorted((SAMPLES / d).iterdir())],
)
def test_all_samples_load(relative):
    result = load(relative)
    assert result.error is None
    assert result.docs and all(d.text for d in result.docs)


def test_corrupt_pdf_returns_error():
    result = load("invalid/corrupt.pdf")
    assert result.error == "Could not read this PDF. It may be damaged."
    assert result.docs == []


def test_encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret", algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    result = load_file("locked.pdf", buf.getvalue())
    assert result.error == "This PDF is password-protected. Remove the password and re-upload."


def test_scanned_pdf_without_text():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    result = load_file("scan.pdf", buf.getvalue())
    assert result.error == "No text found. This looks like a scanned PDF; OCR is not supported."


def test_latin1_txt():
    result = load_file("notes.txt", "Café menu: crème brûlée".encode("latin-1"))
    assert result.error is None
    assert "crème brûlée" in result.docs[0].text


def test_malformed_csv():
    result = load_file("bad.csv", b'name,team\n"Asha,Platform\nRavi,Data\n')
    assert result.error is not None
    assert result.error.startswith("Could not parse CSV:")


def test_damaged_excel():
    result = load_file("broken.xlsx", b"PK\x03\x04" + b"\x00" * 200)
    assert result.error == "Could not read this Excel file. It may be damaged."
