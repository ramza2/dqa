"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the DQA backend.

    Secrets are typed as SecretStr so accidental stringification does not expose
    raw credentials. Catalog Package, Query Template, LLM, and DEMIS execution
    settings are intentionally not wired in this skeleton PR.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="DEMIS Query Assistant", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    dqa_db_host: str = Field(default="localhost", alias="DQA_DB_HOST")
    dqa_db_port: int = Field(default=5432, alias="DQA_DB_PORT")
    dqa_db_name: str = Field(default="dqa", alias="DQA_DB_NAME")
    dqa_db_user: str = Field(default="dqa", alias="DQA_DB_USER")
    dqa_db_password: SecretStr = Field(default=SecretStr("change-me"), alias="DQA_DB_PASSWORD")

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the DQA application PostgreSQL database."""
        password = self.dqa_db_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.dqa_db_user}:{password}"
            f"@{self.dqa_db_host}:{self.dqa_db_port}/{self.dqa_db_name}"
        )

    @property
    def database_url_safe(self) -> str:
        """Connection URL with the password redacted for logs and errors."""
        return (
            f"postgresql+psycopg://{self.dqa_db_user}:***"
            f"@{self.dqa_db_host}:{self.dqa_db_port}/{self.dqa_db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
