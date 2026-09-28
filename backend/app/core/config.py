"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Runtime configuration for the DQA backend.

    Secrets are typed as SecretStr so accidental stringification does not expose
    raw credentials. LLM settings are optional at process start; completeness is
    validated only when ``create_llm_provider`` is called.
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

    # Optional OpenAI-compatible LLM provider (advisory use only).
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_api_key: SecretStr | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_connect_timeout_seconds: float = Field(
        default=10.0, alias="LLM_CONNECT_TIMEOUT_SECONDS"
    )
    # Optional vLLM/Qwen chat-template control. None => omit from wire payload.
    llm_enable_thinking: bool | None = Field(
        default=None, alias="LLM_ENABLE_THINKING"
    )

    @property
    def sqlalchemy_database_url(self) -> URL:
        """SQLAlchemy URL object for the DQA application PostgreSQL database."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.dqa_db_user,
            password=self.dqa_db_password.get_secret_value(),
            host=self.dqa_db_host,
            port=self.dqa_db_port,
            database=self.dqa_db_name,
        )

    @property
    def database_url(self) -> str:
        """Rendered SQLAlchemy URL (password preserved, properly escaped)."""
        return self.sqlalchemy_database_url.render_as_string(hide_password=False)

    @property
    def database_url_safe(self) -> str:
        """Connection URL with the password redacted for logs and errors."""
        return self.sqlalchemy_database_url.render_as_string(hide_password=True)


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
