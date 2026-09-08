# Claude Code Briefing — Phase 2 Addendum: Agent Scope

## Context

Phase 2 (database, auth, agent API) is already built, tested, and merged to main.
This is a small, additive follow-up, not a rebuild — do not modify anything else
from Phase 2 beyond what's described below.

## The gap this fills

`POST /agents/market-insights/run` currently takes no input describing what the
agent should actually research. This product runs continuously against a single
configured scope per agent, not an ad-hoc topic typed fresh each time. That scope
needs somewhere to live, and the run endpoint needs to actually use it.

## What to build

### 1. New table: `agent_scopes`
- tenant_id (foreign key), agent_type, product_line (text, required), competitors
  (text, optional), geography (text, optional), updated_at.
- One scope row per tenant per agent_type. Enforced by tenant_scope.py, same as
  every other table.

### 2. New endpoints
- `GET /agents/market-insights/scope` — returns the current scope for the
  authenticated tenant, or a clear "not configured" response if none exists yet.
- `PUT /agents/market-insights/scope` — creates or updates the scope. Reject the
  request (400, clear error message) if `product_line` is empty or missing —
  competitors and geography stay optional.

### 3. Modify the run endpoint
- `POST /agents/market-insights/run` must now check whether a scope with a
  non-empty `product_line` exists for the tenant before doing anything else.
- If no scope is configured: return an error (400 or 409, your call) with a clear
  message like "Product line must be configured before this agent can run" — do
  NOT silently run against nothing, and do not accept an ad-hoc subject in the
  request body anymore.
- If a scope exists: use its `product_line` (plus `competitors` and `geography`
  if present) as the input to the Phase 1 agent module, replacing the old
  `--subject` CLI argument with these configured values.

## Non-goals

- No frontend changes — that's a separate task.
- No changes to how the Phase 1 agent itself processes its input, only how that
  input gets sourced (from configured scope instead of a raw string).
- No scope configuration for any other agent — Market Insights only, since it's
  the only agent with a real backend right now.

## Success criteria

1. Calling run with no scope configured returns a clear error, not a run.
2. Setting a scope with an empty product_line is rejected.
3. Setting a valid scope, then calling run, succeeds and the agent's research
   actually reflects the configured product_line (and competitors/geography if
   provided) — not a hardcoded or placeholder value.
