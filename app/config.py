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

    @property
    def admin_keys(self) -> set[str]:
        return {k.strip() for k in self.loom_admin_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
