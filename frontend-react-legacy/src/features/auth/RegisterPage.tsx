import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../../lib/apiClient";
import { useAuth, type Role } from "./AuthContext";

const ROLE_HOME: Record<Role, string> = {
  RIDER: "/rider",
  DRIVER: "/driver",
  ADMIN: "/admin",
};

type RegisterableRole = Extract<Role, "RIDER" | "DRIVER">;

export function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<RegisterableRole>("RIDER");
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setErrors(null);
    setIsSubmitting(true);
    try {
      await apiClient.post("/auth/register/", {
        email,
        phone_number: phoneNumber || undefined,
        first_name: firstName,
        last_name: lastName,
        password,
        role,
      });
      const user = await login(email, password);
      navigate(ROLE_HOME[user.role], { replace: true });
    } catch (err) {
      const data = (err as { response?: { data?: Record<string, string[]> } })
        ?.response?.data;
      setErrors(data ?? { non_field_errors: ["Registration failed."] });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Create your account</h1>
      <form onSubmit={handleSubmit} className="auth-form">
        <label htmlFor="role">I am a</label>
        <select
          id="role"
          value={role}
          onChange={(e) => setRole(e.target.value as RegisterableRole)}
        >
          <option value="RIDER">Rider</option>
          <option value="DRIVER">Driver</option>
        </select>

        <label htmlFor="first_name">First name</label>
        <input
          id="first_name"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
        />

        <label htmlFor="last_name">Last name</label>
        <input
          id="last_name"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
        />

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />

        <label htmlFor="phone_number">Phone (optional)</label>
        <input
          id="phone_number"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          autoComplete="tel"
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
        />

        {errors && (
          <ul className="form-error">
            {Object.entries(errors).map(([field, messages]) =>
              messages.map((message, i) => (
                <li key={`${field}-${i}`}>
                  {field}: {message}
                </li>
              )),
            )}
          </ul>
        )}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating account..." : "Register"}
        </button>
      </form>
      <p>
        Already have an account? <a href="/login">Sign in</a>
      </p>
    </div>
  );
}
