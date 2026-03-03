from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str          # server-side; never expose to frontend
    SUPABASE_ANON_KEY: str                  # public key (for client-side JWT verify)
    SUPABASE_JWT_SECRET: str                # from Supabase dashboard → Settings → API

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Cloudflare R2 ─────────────────────────────────────────────────────────
    R2_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str
    R2_PUBLIC_URL: str                      # e.g. https://pub-xxx.r2.dev

    # ── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET: str = "change-me-in-prod"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Rate limiting ─────────────────────────────────────────────────────────
    MATCH_RATE_LIMIT: str = "10/minute"

    # ── APScheduler ──────────────────────────────────────────────────────────
    SCORECARD_SYNC_CRON: str = "0 2 * * 1"     # every Monday 02:00 UTC
    SCORECARD_API_KEY: str = ""                  # optional (higher rate limit)


@lru_cache
def get_settings() -> Settings:
    return Settings()
