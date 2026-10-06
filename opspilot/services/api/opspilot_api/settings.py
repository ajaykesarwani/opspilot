from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_KB_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge_base"


class Settings(BaseSettings):
    """Environment-driven configuration (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "opspilot-api"
    environment: str = "local"
    log_level: str = "INFO"
    # MOCK_MODE only swaps the LLM/embedder for deterministic local ones. It does not change
    # whether Kafka and PostgreSQL are used.
    mock_mode: bool = True
    # Local-development default only; override via DATABASE_URL. Never log this value.
    database_url: str = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot"
    # Host-side address of the Compose broker (containers use kafka:9092).
    kafka_bootstrap_servers: str = "localhost:29092"
    event_backend: Literal["kafka", "memory"] = "kafka"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    knowledge_base_dir: Path = DEFAULT_KB_DIR
