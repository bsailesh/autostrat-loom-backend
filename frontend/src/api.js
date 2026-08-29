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

export const api = {
  base: API_BASE,

  // --- auth ---
  signup: (email, password, tenant_name) =>
    apiFetch("/auth/signup", { method: "POST", body: JSON.stringify({ email, password, tenant_name: tenant_name || "" }) }),
  login: (email, password) =>
    apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiFetch("/auth/me"),
  logout: () => apiFetch("/auth/logout", { method: "POST" }),

  // --- market insights: scope ---
  getScope: () => apiFetch("/agents/market-insights/scope"),
  putScope: ({ product_line, competitors, geography }) =>
    apiFetch("/agents/market-insights/scope", {
      method: "PUT",
      body: JSON.stringify({ product_line, competitors: competitors || "", geography: geography || "" }),
    }),

  // --- market insights: runs & reports ---
  startRun: () => apiFetch("/agents/market-insights/run", { method: "POST", body: "{}" }),
  listRuns: () => apiFetch("/agents/market-insights/runs"),
  getRun: (runId) => apiFetch(`/agents/market-insights/runs/${runId}`),
  listRunReports: (runId) => apiFetch(`/agents/market-insights/runs/${runId}/reports`),
  getReport: (reportId) => apiFetch(`/agents/market-insights/reports/${reportId}`),
};
