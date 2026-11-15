from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.config import settings

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

LOG_FILE = "app.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3
NOISY_LOGGERS = ("httpx", "httpcore", "groq", "urllib3", "sentence_transformers", "huggingface_hub", "faiss")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """JSON lines to logs/app.log (rotating) and the console. Safe to call more than once."""
    root = logging.getLogger()
    if any(getattr(h, "_onboardiq", False) for h in root.handlers):
        return
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(
        settings.log_dir / LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
    )
    console = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, console):
        handler.setFormatter(formatter)
        handler.addFilter(_RequestIdFilter())
        handler._onboardiq = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
