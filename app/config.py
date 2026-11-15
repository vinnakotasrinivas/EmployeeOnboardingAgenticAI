from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    groq_guard_model: str = "openai/gpt-oss-safeguard-20b"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    groq_max_tokens: int = 800  # must stay under the plan's output-tokens-per-minute limit (1000 on free tier)

    max_file_mb: float = 19.0
    top_k: int = 5
    similarity_threshold: float = 0.35
    relevance_threshold: float = 0.75
    off_topic_threshold: float = 0.45
    off_topic_search_threshold: float = 0.50

    api_url: str = "http://127.0.0.1:8766"
    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")

    @field_validator("data_dir", "log_dir")
    @classmethod
    def _anchor_to_project_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def faiss_dir(self) -> Path:
        return self.data_dir / "faiss_index"

    @property
    def registry_db(self) -> Path:
        return self.data_dir / "registry.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def max_file_bytes(self) -> float:
        return self.max_file_mb * 1024 * 1024


settings = Settings()

for _dir in (settings.data_dir, settings.uploads_dir, settings.log_dir):
    _dir.mkdir(parents=True, exist_ok=True)
