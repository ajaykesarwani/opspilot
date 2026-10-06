from pydantic_settings import BaseSettings, SettingsConfigDict

# Local-development default only; override with DATABASE_URL. Never log this value.
DEFAULT_DATABASE_URL = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot"


class DatabaseSettings(BaseSettings):
    """Used by the Alembic CLI; services read DATABASE_URL through their own settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
