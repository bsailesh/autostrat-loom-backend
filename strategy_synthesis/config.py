"""
Strategy Synthesis Agent (Agent 5) configuration.

Mirrors market_insights/config.py exactly: no database, no auth, just an
API key and a model name. Kept independent of app/config.py for the same
reason -- this package doesn't depend on the FastAPI app.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it
    pass


# Opus, not Sonnet, by default: a Pass 1 judgment error propagates
# irreversibly into all seven Pass 2 reports, and this agent runs per
# portfolio-review cycle rather than per initiative, so the cost delta is
# small next to the cost of a wrong recommendation. Override with
# STRATEGY_SYNTHESIS_MODEL=claude-sonnet-5 for cheap iteration while
# debugging the pipeline itself (e.g. the first runs after a deploy) --
# same override pattern as market_insights' --model/MARKET_INSIGHTS_MODEL.
DEFAULT_MODEL = "claude-opus-5"


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
            or os.environ.get("STRATEGY_SYNTHESIS_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        return Settings(anthropic_api_key=api_key, model=model)
