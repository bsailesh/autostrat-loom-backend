"""
Phase 1 configuration.

Kept separate from app/config.py on purpose: this phase has no database, no
auth, no SMTP — just an API key and a model name. Reads a .env file if one is
present (same one the backend uses) but only looks at two keys.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it
    pass


# The synthesis model. Defaults to the strongest generally-available model
# because Phase 1 is a quality bake-off against the hand-built samples, not a
# cost exercise. Override with --model or MARKET_INSIGHTS_MODEL.
DEFAULT_MODEL = "claude-opus-5"

# Web search tool version. The basic variant is supported on every current model
# via the first-party API and is the safe choice; newer dynamic-filtering
# variants can be swapped in here if the installed SDK/model supports them.
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str

    @staticmethod
    def load(model_override: str | None = None) -> "Settings":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in your environment or in a "
                ".env file at the repo root (see .env.example)."
            )
        model = (
            model_override
            or os.environ.get("MARKET_INSIGHTS_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        return Settings(anthropic_api_key=api_key, model=model)
