"""
Base agent.

Every agent subclasses this and gets two things for free:

1. `call_claude_structured(...)` — sends a prompt to Claude with a forced
   tool call whose input_schema matches a Pydantic model, so the response is
   always valid structured data instead of prose we'd have to parse. If
   Claude doesn't return a usable tool call, this raises rather than
   silently returning garbage to the caller.

2. `log(...)` — writes one row to the audit_log table. This is called from
   every agent's `run()` method, so "every agent action is attributed and
   timestamped" is true by construction, not by convention someone has to
   remember.
"""
import json
from typing import TypeVar, Type

from anthropic import Anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, Tenant

T = TypeVar("T", bound=BaseModel)


class AgentError(Exception):
    """Raised when Claude's response can't be turned into the expected structured output."""


class BaseAgent:
    name: str = "base"

    def __init__(self):
        settings = get_settings()
        self._model = settings.loom_model
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def call_claude_structured(
        self,
        *,
        system: str,
        user_prompt: str,
        output_schema: Type[T],
        max_tokens: int = 1500,
    ) -> T:
        tool_name = f"emit_{output_schema.__name__.lower()}"
        tool_def = {
            "name": tool_name,
            "description": f"Return the result as {output_schema.__name__}.",
            "input_schema": output_schema.model_json_schema(),
        }

        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_name},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                try:
                    return output_schema.model_validate(block.input)
                except Exception as e:
                    raise AgentError(f"{self.name}: Claude returned data that failed validation: {e}") from e

        raise AgentError(f"{self.name}: Claude did not return the expected tool call.")

    def log(
        self,
        db: Session,
        *,
        tenant: Tenant,
        actor_label: str,
        action: str,
        input_summary: str,
        output_summary: str,
    ) -> None:
        entry = AuditLog(
            tenant_id=tenant.id,
            actor_label=actor_label,
            agent_name=self.name,
            action=action,
            input_summary=input_summary[:2000],
            output_summary=output_summary[:2000],
        )
        db.add(entry)
        # Deliberately not committing here — caller commits alongside the
        # substantive write in the same transaction, so the audit row and
        # the data change either both land or both roll back together.
