// Single place that knows how to talk to the Phase 2 FastAPI backend.
// Session shape/key match the existing marketing index.html so both can coexist.

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

const SESSION_KEY = "loom_session";

export function getSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export function setSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}
export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

// Thrown for any non-2xx; carries the backend's `detail` string and status.
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch(path, options = {}) {
  const session = getSession();
  const resp = await fetch(API_BASE + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: "Bearer " + session.token } : {}),
      ...(options.headers || {}),
    },
  });

  if (resp.status === 401) {
    clearSession();
    // Let the AuthProvider react and bounce to /login.
    window.dispatchEvent(new Event("loom:unauthorized"));
    throw new ApiError("Your session has expired — please sign in again.", 401);
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body && body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, resp.status);
  }

  if (resp.status === 204) return null;
  return resp.json();
}

// Shared by every agent's docx export: not JSON, so it doesn't go through
// apiFetch. Returns {blob, filename} for the caller to trigger a download.
async function fetchDocx(path) {
  const session = getSession();
  const resp = await fetch(API_BASE + path, {
    headers: session ? { Authorization: "Bearer " + session.token } : {},
  });
  if (resp.status === 401) {
    clearSession();
    window.dispatchEvent(new Event("loom:unauthorized"));
    throw new ApiError("Your session has expired — please sign in again.", 401);
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body && body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, resp.status);
  }
  const disposition = resp.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match ? match[1] : "export.docx";
  const blob = await resp.blob();
  return { blob, filename };
}

export const api = {
  base: API_BASE,

  // --- auth (shared across all agents) ---
  signup: (email, password, tenant_name) =>
    apiFetch("/auth/signup", { method: "POST", body: JSON.stringify({ email, password, tenant_name: tenant_name || "" }) }),
  login: (email, password) =>
    apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiFetch("/auth/me"),
  logout: () => apiFetch("/auth/logout", { method: "POST" }),

  // Each agent's own namespace -- kept separate so one agent's endpoints
  // can change without touching another's call sites (see
  // frontend/src/reportWorkspace/ for what's actually shared).
  marketInsights: {
    getScope: () => apiFetch("/agents/market-insights/scope"),
    putScope: ({ product_line, competitors, geography }) =>
      apiFetch("/agents/market-insights/scope", {
        method: "PUT",
        body: JSON.stringify({ product_line, competitors: competitors || "", geography: geography || "" }),
      }),

    startRun: () => apiFetch("/agents/market-insights/run", { method: "POST", body: "{}" }),
    listRuns: () => apiFetch("/agents/market-insights/runs"),
    getRun: (runId) => apiFetch(`/agents/market-insights/runs/${runId}`),
    listRunReports: (runId) => apiFetch(`/agents/market-insights/runs/${runId}/reports`),
    getReport: (reportId) => apiFetch(`/agents/market-insights/reports/${reportId}`),
    exportRunDocx: (runId) => fetchDocx(`/agents/market-insights/runs/${runId}/export.docx`),
  },

  strategySynthesis: {
    startRun: (payload) => apiFetch("/agents/strategy/runs", { method: "POST", body: JSON.stringify(payload || {}) }),
    listRuns: () => apiFetch("/agents/strategy/runs"),
    getRun: (runId) => apiFetch(`/agents/strategy/runs/${runId}`),
    listRunReports: (runId) => apiFetch(`/agents/strategy/runs/${runId}/reports`),
    getReport: (reportId) => apiFetch(`/agents/strategy/reports/${reportId}`),
    exportRunDocx: (runId) => fetchDocx(`/agents/strategy/runs/${runId}/export.docx`),
    getReadiness: () => apiFetch("/agents/strategy/readiness"),

    getBuckets: () => apiFetch("/agents/strategy/buckets"),
    putBuckets: (buckets) => apiFetch("/agents/strategy/buckets", { method: "PUT", body: JSON.stringify({ buckets }) }),

    getConfig: () => apiFetch("/agents/strategy/config"),
    putConfig: (config) => apiFetch("/agents/strategy/config", { method: "PUT", body: JSON.stringify(config) }),

    getObjectives: () => apiFetch("/agents/strategy/objectives"),
    putObjectives: (objectives) => apiFetch("/agents/strategy/objectives", { method: "PUT", body: JSON.stringify({ objectives }) }),

    getProposals: () => apiFetch("/agents/strategy/proposals"),
    putProposals: (proposals) => apiFetch("/agents/strategy/proposals", { method: "PUT", body: JSON.stringify({ proposals }) }),

    getFramework: () => apiFetch("/agents/strategy/framework"),
    putFramework: (framework) => apiFetch("/agents/strategy/framework", { method: "PUT", body: JSON.stringify(framework) }),

    getScenarios: () => apiFetch("/agents/strategy/scenarios"),
    putScenarios: (scenarios) => apiFetch("/agents/strategy/scenarios", { method: "PUT", body: JSON.stringify({ scenarios }) }),

    listFiles: () => apiFetch("/agents/strategy/files"),
    getTemplate: async (fileType) => {
      const session = getSession();
      const resp = await fetch(API_BASE + `/agents/strategy/templates/${fileType}`, {
        headers: session ? { Authorization: "Bearer " + session.token } : {},
      });
      if (!resp.ok) throw new ApiError(resp.statusText, resp.status);
      const disposition = resp.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^";]+)"?/);
      const filename = match ? match[1] : `${fileType}_template.csv`;
      const blob = await resp.blob();
      return { blob, filename };
    },
    uploadFile: (fileType, file, { asOf, uploadedBy } = {}) => {
      const session = getSession();
      const form = new FormData();
      form.append("file", file);
      if (asOf) form.append("as_of", asOf);
      if (uploadedBy) form.append("uploaded_by", uploadedBy);
      return fetch(API_BASE + `/agents/strategy/files/${fileType}`, {
        method: "POST",
        headers: session ? { Authorization: "Bearer " + session.token } : {},
        body: form,
      }).then(async (resp) => {
        if (resp.status === 401) {
          clearSession();
          window.dispatchEvent(new Event("loom:unauthorized"));
          throw new ApiError("Your session has expired — please sign in again.", 401);
        }
        const body = await resp.json().catch(() => null);
        if (!resp.ok) {
          const detail = body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : resp.statusText;
          throw new ApiError(detail, resp.status);
        }
        return body;
      });
    },

    listCandidates: () => apiFetch("/agents/strategy/candidates"),
    patchCandidate: (key, payload) =>
      apiFetch(`/agents/strategy/candidates/${key}`, { method: "PATCH", body: JSON.stringify(payload) }),
    scopeCandidate: (key, payload) =>
      apiFetch(`/agents/strategy/candidates/${key}/scope`, { method: "POST", body: JSON.stringify(payload) }),
  },
};
