"""
Technology & Regulatory Intelligence Agent (Agent 3) configuration.

Mirrors market_insights/config.py: no database, no auth, just an API key, a
model name and the web-search tool version. Kept independent of
app/config.py for the same reason the other two agent packages are --
nothing in here depends on the FastAPI app.

WEB_SEARCH_TOOL_TYPE is re-declared here rather than imported from
market_insights.config on purpose. The agent packages do not import each
other (strategy_synthesis duplicates its own ReportSpec rather than
importing Market Insights'), so one agent's tool-version bump can never
silently change another's research behaviour.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars still work without it
    pass


# Opus by default, as with the other two agents. This agent's judgment calls
# are applicability calls -- does this regulation bind this customer, given
# their certification basis -- and a wrong one is a finding the customer acts
# on or ignores incorrectly. Override with TECH_REGULATION_MODEL for cheap
# iteration while debugging the pipeline itself.
DEFAULT_MODEL = "claude-opus-5"

# Web search tool version. The basic variant is supported on every current
# model via the first-party API and is the safe choice; newer
# dynamic-filtering variants can be swapped in here if the installed
# SDK/model supports them.
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
            or os.environ.get("TECH_REGULATION_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        return Settings(anthropic_api_key=api_key, model=model)
