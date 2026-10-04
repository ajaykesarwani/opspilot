from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Environment-driven configuration for the worker."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "opspilot-worker"
    environment: str = "local"
    log_level: str = "INFO"
    mock_mode: bool = True
    database_url: str = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot"
    kafka_bootstrap_servers: str = "localhost:9092"
    consumer_group_id: str = "opspilot-worker-group"
