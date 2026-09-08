# Claude Code Kickoff Briefing — Phase 5: Frontend / Report Workspace

## Goal

Build the real, logged-in frontend: login/signup calling the Phase 2 auth API, a
home dashboard, and a report workspace where a user reads Market Insights agent
output. This replaces the current demo login (hardcoded client-side password) and
the static HTML mockups entirely.

Do not start this until Phase 2 (database, auth, agent API) is built and tested —
this phase calls those endpoints directly and can't be meaningfully built without
them working first.

## Reference file — use this, don't redesign from scratch

`autostrat-loom-dashboard.jsx` is attached alongside this briefing. It's a working
React component with the actual agreed design system already built: the theme object
(navy `#1B2A4A`, orange `#E8703A`, IBM Plex-style type scale), the persistent icon
rail, the Settings sidebar pattern, and shared components (`Card`, `Badge`, `Button`,
`Row`). Treat this as the starting design system, not just a rough sketch — colors,
spacing, and component patterns should carry over exactly. Its Home dashboard and
agent-card logic (Active / Not subscribed / Running states) are already correct and
should be adapted to call real API data instead of the hardcoded state it currently
uses.

## What to build

### 1. Login / Signup
- Real login form calling Phase 2's login endpoint, replacing the demo's hardcoded
  `demo@autostrat.net` / `LoomDemo2026` check entirely.
- A signup flow calling Phase 2's signup endpoint. Per the existing product decision,
  there is no "individual vs organization" choice shown to the user — signing up
  always creates a tenant silently, with the signing-up user as owner.
- Store the returned session token and attach it as a bearer token on all subsequent
  API calls.

### 2. Home dashboard
- Same agent-card grid as the reference file. For now, only **Market Insights** has
  a real backend — its card should be genuinely interactive (Active, Run button,
  running/spinner state, last-run timestamp, pulled from real API data).
- The other four agents (Voice of Customer, Tech & Regulation, Product Sustainment,
  Strategy Synthesis and Decision) should render in their existing "Not subscribed"
  visual state from the reference file — do not make them interactive or wire them
  to anything, they have no backend yet.

### 3. Configure scope (required before the agent can run)

This is new since the original briefing was written: the agent runs continuously
against one configured scope per tenant, not an ad-hoc topic. A companion backend
addendum (`phase2_addendum_scope.md`) adds `GET`/`PUT /agents/market-insights/scope`
and makes the run endpoint reject requests until a scope with a non-empty
`product_line` exists. The frontend must respect this gate, not just call run and
handle the error reactively.

- **First-time flow**: when a tenant has no scope configured yet, clicking into the
  Market Insights agent (or clicking Run) should show a Configure Scope form before
  anything else — not let them reach a Run button that will just fail.
- **Fields**: Product line / market focus (required, textarea — this is the core
  input, encourage real detail, not a one-word answer), Known competitors (optional,
  textarea or simple tag input), Geographic focus (optional, text input).
- **Validation**: Product line cannot be empty — disable the Save/Continue button
  until it has content, mirroring the backend's own validation rather than only
  relying on a server error message.
- **Editable later**: this same form should be reachable afterward from the
  "Configure" gear icon on the agent card (matching the existing per-agent
  Configure Sources pattern already in the reference design) so a customer can
  update their scope, not just set it once at signup.
- **Run button behavior**: once a scope exists, the Run button on both the home
  dashboard card and the report workspace top bar works as originally described.
  If no scope exists, the Run button should be disabled or replaced with a
  "Set up this agent" prompt that leads to the Configure Scope form — the user
  should never be able to click Run and get an error back; the UI should prevent
  the invalid state, not just handle it after the fact.

### 4. Report workspace (Market Insights)
Clicking into the Market Insights card opens a workspace with this exact layout:

- **Left sidebar**: list of the 9 reports by name (Executive Summary, Market
  Landscape, Competitor Intelligence, Feature Comparison, Customer Demand, Market
  Trends, Market SWOT, Intelligence Digest, Industry Trends), pulled from the run's
  actual report list via the Phase 2 API. Clicking a report shows it in the main panel.
- **Top bar**: agent name, last-run timestamp, a run-history dropdown (populated from
  `GET /agents/market-insights/runs`), and a Run button that calls the run endpoint
  and shows a loading/running state until it completes.
- **Main panel, Report 1 (Executive Summary) only**: opens with a **Governing Insight**
  box — visually distinct (accent left border), showing the Situation / Complication /
  Question / Answer structure as separate labeled lines, per the agent's actual output
  format.
- **Main panel, every other report**: opens with a **Key Insights box** — 4-5 bullets,
  each ending with its confidence tag (High/Medium/Low, color-coded: green/amber/red),
  per the agent's actual output format. Do not add a Governing Insight box to these —
  that's Report 1 only, by design.
- **Every finding shown anywhere in a report** carries its confidence tag inline, and
  where the agent's output includes a "so what" implication line, render it visually
  distinct from the finding itself (e.g. italic, slightly indented) — the two are not
  the same and shouldn't be visually merged.
- **Exhibits**: where the agent's output includes structured data suited to a named
  visual (the TAM/SAM/SOM breakdown, the Harvey Ball competitive grid, the trend
  table, the 3-column Industry Trends format), render it as that visual, not as plain
  text — the agent's spec defines specific exhibit types per report, use them.

## API integration
- `POST /auth/signup`, `POST /auth/login`
- `POST /agents/market-insights/run`
- `GET /agents/market-insights/runs`
- `GET /agents/market-insights/runs/{run_id}/reports`
- `GET /agents/market-insights/reports/{report_id}`

If any of these don't match what Phase 2 actually built, treat that as a signal to
check with me before guessing at a workaround — the two phases need to agree on the
same contract.

## Explicit non-goals for this phase

- No settings/billing/data-source screens — those exist as separate designs, not
  part of this task.
- No UI for the other four agents beyond their existing static "Not subscribed" card.
- No deployment — this phase is about the code being correct and running locally
  (or in a dev environment), not live on autostrat.net. Deployment is Phase 6.
- No changes to the Phase 1 agent logic or Phase 2 backend — this phase only calls
  what already exists.

## Success criteria

I should be able to: sign up, land on the home dashboard, click Market Insights,
click Run, watch it move through a loading state, then browse all 9 reports with
Report 1 showing a Governing Insight box, every other report showing a Key Insights
box with confidence tags, and the named exhibits rendering as actual visuals — not
plain text — wherever the agent's output calls for them.
