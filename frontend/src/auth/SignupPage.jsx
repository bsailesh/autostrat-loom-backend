import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";
import { AuthShell, TextInput, FormError } from "./AuthShell.jsx";
import { Button } from "../components/atoms.jsx";
import { theme } from "../theme.js";

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const passwordOk = password.length >= 8;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      // Per the product decision, there's no "individual vs organization" choice
      // here — signup always creates a tenant with this user as its owner.
      await signup(email.trim(), password, workspace.trim());
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.status === 409 ? "An account with this email already exists." : err.message || "Sign up failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Sets up your workspace so your team can share agent output."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" style={{ color: theme.orange, fontWeight: 600 }}>
            Sign in
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
          autoComplete="new-password"
        />
        {password.length > 0 && !passwordOk && (
          <p style={{ fontSize: 11, color: theme.textMuted, margin: "-8px 0 12px" }}>
            At least 8 characters.
          </p>
        )}
        <TextInput
          label="Workspace name (optional)"
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          placeholder="e.g. Acme Industrial"
        />
        <Button
          type="submit"
          variant="primary"
          disabled={busy || !email.trim() || !passwordOk}
          style={{ width: "100%", justifyContent: "center", marginTop: 4 }}
        >
          {busy ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
