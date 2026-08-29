import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, clearSession, getSession, setSession } from "../api.js";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSessionState] = useState(() => getSession());
  const [ready, setReady] = useState(false);

  // On boot, validate a stored token against the backend so a stale/expired
  // token doesn't leave the app in a half-logged-in state.
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      const existing = getSession();
      if (!existing) {
        setReady(true);
        return;
      }
      try {
        await api.me();
        if (!cancelled) setSessionState(existing);
      } catch {
        if (!cancelled) {
          clearSession();
          setSessionState(null);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    }
    validate();
    return () => {
      cancelled = true;
    };
  }, []);

  // apiFetch fires this on any 401.
  useEffect(() => {
    function onUnauthorized() {
      setSessionState(null);
    }
    window.addEventListener("loom:unauthorized", onUnauthorized);
    return () => window.removeEventListener("loom:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password);
    setSession(data);
    setSessionState(data);
    return data;
  }, []);

  const signup = useCallback(async (email, password, tenantName) => {
    const data = await api.signup(email, password, tenantName);
    setSession(data);
    setSessionState(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* best effort */
    }
    clearSession();
    setSessionState(null);
  }, []);

  const value = useMemo(
    () => ({ session, ready, isAuthed: !!session, login, signup, logout }),
    [session, ready, login, signup, logout]
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
