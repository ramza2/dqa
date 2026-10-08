"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

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
    # Parameter Extraction may send raw NL request text to the LLM only when true.
    # Default false: technical opt-in gate, not a production data-egress approval.
    llm_parameter_extraction_allow_raw_request: bool = Field(
        default=False,
        alias="LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST",
    )
    # Separate production policy approval gate. Both this and the technical
    # raw-request opt-in must be true before request text may leave DQA.
    llm_parameter_extraction_raw_request_egress_approved: bool = Field(
        default=False,
        alias="LLM_PARAMETER_EXTRACTION_RAW_REQUEST_EGRESS_APPROVED",
    )
    # Authentication provider. Default disabled = fail-closed on protected routes.
    # ``dev_headers`` is development/test only and rejected outside those envs.
    dqa_auth_provider: Literal["disabled", "dev_headers"] = Field(
        default="disabled",
        alias="DQA_AUTH_PROVIDER",
    )
    # Dedicated env-var prefix for DEMIS Connection Profile credential refs
    # (``env:<NAME>``). Only names starting with this prefix may be resolved.
    dqa_demis_credential_env_prefix: str = Field(
        default="DEMIS_SECRET_",
        alias="DQA_DEMIS_CREDENTIAL_ENV_PREFIX",
    )

    # Optional OpenAI-compatible Embedding provider (Data Discovery).
    # Startup succeeds without these; completeness is checked at provider create.
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    embedding_api_key: SecretStr | None = Field(default=None, alias="EMBEDDING_API_KEY")
    embedding_model: str | None = Field(default=None, alias="EMBEDDING_MODEL")
    embedding_model_revision: str | None = Field(
        default=None, alias="EMBEDDING_MODEL_REVISION"
    )
    embedding_dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")
    embedding_normalize: bool = Field(default=True, alias="EMBEDDING_NORMALIZE")
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")
    embedding_timeout_seconds: float = Field(
        default=60.0, alias="EMBEDDING_TIMEOUT_SECONDS"
    )
    embedding_connect_timeout_seconds: float = Field(
        default=10.0, alias="EMBEDDING_CONNECT_TIMEOUT_SECONDS"
    )
    embedding_query_prefix: str | None = Field(
        default=None, alias="EMBEDDING_QUERY_PREFIX"
    )
    embedding_document_prefix: str | None = Field(
        default=None, alias="EMBEDDING_DOCUMENT_PREFIX"
    )

    data_discovery_search_rrf_k: int = Field(
        default=60, alias="DATA_DISCOVERY_SEARCH_RRF_K"
    )
    data_discovery_search_candidate_multiplier: int = Field(
        default=3, alias="DATA_DISCOVERY_SEARCH_CANDIDATE_MULTIPLIER"
    )
    data_discovery_search_candidate_min: int = Field(
        default=20, alias="DATA_DISCOVERY_SEARCH_CANDIDATE_MIN"
    )
    data_discovery_medical_terms_path: str | None = Field(
        default=None, alias="DATA_DISCOVERY_MEDICAL_TERMS_PATH"
    )

    # MCP server foundation (Phase 28-A). Disabled by default.
    # Enabling mounts Streamable HTTP under ``dqa_mcp_mount_path`` on the shared
    # backend ASGI app. This does **not** create a separate listen socket.
    # ``dqa_mcp_bind_host`` is a required private-boundary *declaration* (must be
    # loopback) — it does not configure Uvicorn bind. Non-loopback values refuse
    # the MCP mount (fail closed). Request peers are also restricted to loopback.
    # Production IdP / trusted gateway requirements are not satisfied by
    # ``dev_headers`` — keep disabled until an approved IdentityProvider exists.
    dqa_mcp_enabled: bool = Field(default=False, alias="DQA_MCP_ENABLED")
    dqa_mcp_mount_path: str = Field(default="/mcp", alias="DQA_MCP_MOUNT_PATH")
    dqa_mcp_bind_host: str = Field(default="127.0.0.1", alias="DQA_MCP_BIND_HOST")
    dqa_mcp_max_body_bytes: int = Field(
        default=1_048_576,
        alias="DQA_MCP_MAX_BODY_BYTES",
        ge=1024,
        le=8_388_608,
    )
    # Phase 28-C Template Query MCP path. Execution remains opt-in and disabled
    # by default until an approved production IdP / trusted gateway exists.
    # Token key is required to issue/verify opaque execution tokens (no default).
    dqa_mcp_query_execution_enabled: bool = Field(
        default=False, alias="DQA_MCP_QUERY_EXECUTION_ENABLED"
    )
    dqa_mcp_execution_token_key: SecretStr | None = Field(
        default=None, alias="DQA_MCP_EXECUTION_TOKEN_KEY"
    )
    dqa_mcp_execution_token_ttl_seconds: int = Field(
        default=300,
        alias="DQA_MCP_EXECUTION_TOKEN_TTL_SECONDS",
        ge=30,
        le=300,
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
