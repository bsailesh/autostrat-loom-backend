import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";
import { AuthShell, TextInput, FormError } from "./AuthShell.jsx";
import { Button } from "../components/atoms.jsx";
import { theme } from "../theme.js";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.status === 401 ? "Incorrect email or password." : err.message || "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Access your workspace and agent reports."
      footer={
        <>
          New to AutoStrat Loom?{" "}
          <Link to="/signup" style={{ color: theme.orange, fontWeight: 600 }}>
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit}>
        <FormError>{error}</FormError>
        <TextInput
          label="Work email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
          autoComplete="email"
        />
        <TextInput
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <Button
          type="submit"
          variant="primary"
          disabled={busy || !email.trim() || !password}
          style={{ width: "100%", justifyContent: "center", marginTop: 4 }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  );
}
