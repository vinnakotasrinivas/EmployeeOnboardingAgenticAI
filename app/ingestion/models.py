from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ValidationResult:
    ok: bool
    code: str
    message: str
    file_type: str | None
    size_bytes: int


@dataclass
class LoadedDoc:
    text: str
    metadata: dict[str, Any]


@dataclass
class LoadResult:
    docs: list[LoadedDoc] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    error: str | None = None
