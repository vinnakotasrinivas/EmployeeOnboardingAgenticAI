import pandas as pd
import tiktoken

from app.config import PROJECT_ROOT
from app.ingestion.chunker import CHUNK_TOKENS, TABLE_ROWS_PER_CHUNK, chunk
from app.ingestion.loaders import load_file
from app.ingestion.models import LoadedDoc, LoadResult

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
REQUIRED = {"doc_id", "source", "category", "file_type", "chunk_id"}


def load(relative: str) -> LoadResult:
    path = SAMPLES / relative
    return load_file(path.name, path.read_bytes())


def test_prose_chunks_respect_token_size_and_keep_pages():
    docs = chunk(load("pdf/employee_handbook.pdf"), "doc1", "hr_policy")
    enc = tiktoken.get_encoding("cl100k_base")
    assert len(docs) >= 3
    assert all(len(enc.encode(d.page_content)) <= CHUNK_TOKENS for d in docs)
    assert {d.metadata["page"] for d in docs} == {1, 2, 3}
    assert all(REQUIRED <= d.metadata.keys() for d in docs)


def test_long_text_is_split_with_overlap():
    text = " ".join(f"Sentence {i} about the onboarding policy." for i in range(600))
    result = LoadResult(docs=[LoadedDoc(text=text, metadata={"source": "long.txt", "file_type": "txt"})])
    docs = chunk(result, "doc2", "hr_policy")
    assert len(docs) > 1
    tail = docs[0].page_content[-60:]
    assert tail.split()[-1] in docs[1].page_content


def test_csv_chunks_have_header_and_row_ranges():
    docs = chunk(load("csv/team_directory.csv"), "dir", "team_directory")
    assert len(docs) == -(-184 // TABLE_ROWS_PER_CHUNK)
    first, last = docs[0], docs[-1]
    assert first.page_content.startswith("Source: team_directory.csv, rows 1-25")
    assert "| employee_id" in first.page_content and "| employee_id" in last.page_content
    assert (last.metadata["row_start"], last.metadata["row_end"]) == (176, 184)
    assert first.metadata["file_type"] == "csv"


def test_excel_chunks_name_the_sheet():
    docs = chunk(load("xlsx/training_schedule.xlsx"), "ts", "training_schedule")
    sheets = {d.metadata["sheet"] for d in docs}
    assert sheets == {"Course Catalog", "Session Schedule", "New Hire Assignments"}
    assert docs[0].page_content.startswith("Source: training_schedule.xlsx, sheet Course Catalog, rows 1-18")
    assert all(d.metadata["file_type"] == "xlsx" for d in docs)


def test_chunk_ids_are_unique_and_prefixed():
    df = pd.DataFrame({"a": range(60)})
    docs = chunk(LoadResult(tables={"t.csv:data": df}), "abc", "other")
    assert [d.metadata["chunk_id"] for d in docs] == ["abc:0", "abc:1", "abc:2"]
    assert all(d.id == d.metadata["chunk_id"] for d in docs)
