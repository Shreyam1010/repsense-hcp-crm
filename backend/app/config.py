"""Settings, loaded from the repo-root .env. One DATABASE_URL in; two DSNs out
(SQLAlchemy needs the asyncpg driver; the LangGraph checkpointer needs psycopg)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV, extra="ignore")

    groq_api_key: str = Field("gsk_replace_me", alias="GROQ_API_KEY")
    groq_agent_model: str = Field("openai/gpt-oss-120b", alias="GROQ_AGENT_MODEL")
    groq_extract_model: str = Field("openai/gpt-oss-20b", alias="GROQ_EXTRACT_MODEL")

    database_url: str = Field(
        "postgresql://app_user:app@localhost:5432/repsense", alias="DATABASE_URL"
    )
    cors_origins: str = Field("http://localhost:5173", alias="CORS_ORIGINS")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    rep_id: str = "REP-001"
    territory_id: str = "IN-South-02"

    @property
    def sqlalchemy_dsn(self) -> str:
        """postgresql+asyncpg://... for the SQLAlchemy async engine."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def checkpointer_dsn(self) -> str:
        """psycopg-style DSN for AsyncPostgresSaver.from_conn_string()."""
        return self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_key_looks_real(self) -> bool:
        return self.groq_api_key.startswith("gsk_") and "replace_me" not in self.groq_api_key

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
