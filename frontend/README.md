# AutoStrat Loom — Frontend (Phase 5)

The logged-in product: signup / login, a home dashboard, and the Market Insights
report workspace. It talks directly to the Phase 2 FastAPI backend.

The marketing site (`../index.html`) is unchanged and separate — this app is only
the authenticated experience.

## Stack

- Vite + React 18 (plain JSX, no TypeScript)
- `react-router-dom` for views, `react-markdown` + `remark-gfm` for report bodies,
  `lucide-react` for icons
- Design system (`src/theme.js`, `src/components/atoms.jsx`) carried over from
  `../autostrat-loom-dashboard.jsx`
- No CSS framework — inline styles from the theme object, matching the reference

## Run it

Requires Node 18+.

```bash
cd frontend
cp .env.example .env         # adjust VITE_API_BASE if your backend isn't on :8000
npm install
npm run dev                  # http://localhost:5173
```

The backend must be running separately (`uvicorn app.main:app --reload` from the
repo root) and its `CORS_ORIGINS` must allow the dev origin — the default `*` is
fine for local work.

```bash
npm run build && npm run preview   # production build check
```

## Configuration

`VITE_API_BASE` (default `http://127.0.0.1:8000`) is the only setting. The app
calls the API cross-origin and relies on CORS; there is no dev proxy.

## What it does

| Area | Endpoint(s) |
|---|---|
| Signup / login / session restore | `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` |
| Configure scope (gate before running) | `GET` / `PUT /agents/market-insights/scope` |
| Run + history | `POST /agents/market-insights/run`, `GET .../runs`, `GET .../runs/{id}` |
| Report workspace | `GET .../runs/{id}/reports`, `GET .../reports/{id}` |

- **Scope gate**: if no scope with a non-empty `product_line` exists, the UI sends
  you to the Configure Scope form first — the Run button is never shown in a state
  where it would 409. The Save button is disabled until `product_line` has content,
  mirroring the backend's own rule. The form is reachable later from the gear icon
  on the agent card and in the workspace top bar.
- **Report rendering**: report bodies are the agent's Markdown. Report 1's
  Governing Insight (SCQA) and every other report's Key Insights box are detected
  and rendered as dedicated boxes; confidence tags (`**[High]**` etc.) render as
  green/amber/red pills; `*so what: …*` lines render in an accent style; the
  agent's own tables and the TAM/SAM/SOM ASCII block are themed as exhibits. This
  is heuristic parsing of prose — see `src/marketInsights/insights.js` — so wording
  changes in the agent output can degrade the boxes gracefully back to plain
  Markdown.

## Trying it end to end

A real run does live web research and takes **30–60 minutes**. To exercise the
workspace faster, POST a run with a cheaper model via the API directly:

```bash
curl -X POST $API/agents/market-insights/run \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-5","research_rounds":1}'
```

The UI polls `GET .../runs/{id}` every 6s and loads the reports when the run
reports `succeeded`.

## Layout

```
src/
  api.js                 fetch wrapper + endpoint methods + session storage
  theme.js               palette, fonts, confidence-tone helper
  App.jsx                routes + auth gate + app shell
  auth/                  AuthContext, Login, Signup
  home/HomeDashboard     agent-card grid (Market Insights live, others static)
  components/             Badge / Button / Card / IconRail / PageHeader / ConfidenceTag
  marketInsights/
    useMarketInsights.js  scope + runs + polling hook
    ConfigureScope.jsx    the scope form
    Workspace.jsx         sidebar + top bar + run history + main panel
    ReportView.jsx        one report: strap, insight box, body
    insights.js           prose -> {governing insight | key insights} + remaining body
    markdown.jsx          themed react-markdown (tags, so-what, tables, exhibits)
    InsightBoxes.jsx      GoverningInsightBox / KeyInsightsBox
```
