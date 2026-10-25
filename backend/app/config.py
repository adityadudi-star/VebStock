"""Runtime settings, read from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    # SQLite fallback for local development only; use PostgreSQL in production.
    database_url: str = "sqlite:///" + (BASE_DIR / "data" / "dev.db").as_posix()
    # Comma-separated list of allowed browser origins (the Vercel URL + local dev).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Optional regex for Vercel preview deployments, e.g. https://vebstock-.*\.vercel\.app
    cors_origin_regex: str = ""
    model_dir: str = str(BASE_DIR / "data" / "models")
    environment: str = "development"
    log_level: str = "INFO"
    llm_api_key: str = ""  # optional; enables the LLM assistant
    # Role-based access. When true (default) every data endpoint needs a signed bearer token whose role is allowed.
    # Set AUTH_REQUIRED=false only for local development or automated tests of the pre-existing endpoints.
    auth_required: bool = True
    # HMAC key for session tokens. Required in production; in development a random per-process key is used
    # (tokens then stop working when the API restarts).
    auth_secret: str = ""
    auth_token_hours: int = 12

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def normalized_db_url(self) -> str:
        url = self.database_url
        # Render/Heroku style URLs -> SQLAlchemy + psycopg3 driver
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
