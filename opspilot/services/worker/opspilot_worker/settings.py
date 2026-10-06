from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_KB_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge_base"


class Settings(BaseSettings):
    """Environment-driven configuration for the worker."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "opspilot-worker"
    environment: str = "local"
    log_level: str = "INFO"
    mock_mode: bool = True  # swaps LLM/embedder only; Kafka and PostgreSQL are always real
    database_url: str = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot"
    kafka_bootstrap_servers: str = "localhost:29092"
    consumer_group_id: str = "opspilot-worker-group"
    knowledge_base_dir: Path = DEFAULT_KB_DIR
    metrics_port: int = 9100

    # Retry policy for workflow execution failures.
    max_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    # How long to wait for the API to mark a request QUEUED (event can outrun the DB update).
    queued_wait_polls: int = 20
    queued_wait_interval_seconds: float = 0.5
