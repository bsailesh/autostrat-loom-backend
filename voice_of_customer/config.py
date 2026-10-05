"""
Voice of Customer Agent (Agent 1) configuration.

Mirrors tech_regulation/config.py: an API key, a model name and the
web-search tool version, independent of app/config.py.

WEB_SEARCH_TOOL_TYPE is declared here rather than imported from
market_insights.config or tech_regulation.config. The agent packages do not
import each other, so one agent's tool-version bump can never silently
change another's research behaviour.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it
    pass


# Opus by default, as with the other agents. Override with
# VOICE_OF_CUSTOMER_MODEL for cheap iteration on the pipeline itself.
DEFAULT_MODEL = "claude-opus-5"

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
            or os.environ.get("VOICE_OF_CUSTOMER_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        return Settings(anthropic_api_key=api_key, model=model)
