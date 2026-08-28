"""
Market Insights Agent — Phase 1 (standalone, command-line-testable).

This package is deliberately decoupled from the FastAPI app, the database, and
auth. Phase 1's only job is to prove the agent produces good, spec-compliant
output as real code, runnable with:

    python run_agent.py --subject "some market topic"

Later phases add persistence (Phase 2), API responses (Phase 3), and the rest.
Nothing in here imports from `app/`.
"""

from market_insights.agent import MarketInsightsAgent, AgentRunResult

__all__ = ["MarketInsightsAgent", "AgentRunResult"]
