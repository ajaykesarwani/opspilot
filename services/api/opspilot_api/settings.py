from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "opspilot-api"
    environment: str = "local"
    log_level: str = "INFO"
    mock_mode: bool = True
    # Local-development default only; override via DATABASE_URL. Never log this value.
    database_url: str = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot"
    kafka_bootstrap_servers: str = "localhost:9092"

