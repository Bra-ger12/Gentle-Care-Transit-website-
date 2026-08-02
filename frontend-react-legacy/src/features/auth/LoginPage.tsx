import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, type Role } from "./AuthContext";

const ROLE_HOME: Record<Role, string> = {
  RIDER: "/rider",
  DRIVER: "/driver",
  ADMIN: "/admin",
};

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await login(identifier, password);
      navigate(ROLE_HOME[user.role], { replace: true });
    } catch {
      setError("Invalid email/phone or password.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Gentle Care Transit</h1>
      <form onSubmit={handleSubmit} className="auth-form">
        <label htmlFor="identifier">Email or phone</label>
        <input
          id="identifier"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          autoComplete="username"
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <p className="form-error">{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <p>
        Don&apos;t have an account? <a href="/register">Register</a>
      </p>
    </div>
  );
}
