"""
Central configuration. Everything environment-specific lives here and nowhere
else, so moving from local SQLite to a hosted Postgres instance, or rotating
the Anthropic API key, never requires touching business logic.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    loom_model: str = "claude-sonnet-5"
    database_url: str = "sqlite:///./loom.db"
    loom_admin_keys: str = "admin-dev-key-change-me"

    # Session tokens minted by /auth/login expire after this many hours.
    session_ttl_hours: int = 24

    # --- Contact form email delivery ---
    # If smtp_host is empty, the app still stores every contact submission
    # in the database but skips the actual send (and logs a warning) — so
    # local development never fails just because email isn't configured.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@autostrat.net"
    smtp_use_tls: bool = True
    contact_email_to: str = "saileshathreya@autostrat.net"

    # Comma-separated list of origins allowed to call this API from a
    # browser. "*" is fine for local development; restrict this to your
    # real front-end domain(s) before going to production.
    cors_origins: str = "*"

    @property
    def admin_keys(self) -> set[str]:
        return {k.strip() for k in self.loom_admin_keys.split(",") if k.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
