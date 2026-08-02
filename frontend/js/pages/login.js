import { login, ROLE_HOME } from "../api/auth.js";
import { qs } from "../ui/dom.js";
import { setFieldError, clearFieldError } from "../ui/validation.js";

const form = qs("#login-form");
const submitBtn = qs("#submit-btn");
const submitSpinner = qs("#submit-spinner");
const submitLabel = qs("#submit-label");
const errorEl = qs("#error");
const identifierInput = qs("#identifier");
const passwordInput = qs("#password");

qs("#password-toggle").addEventListener("click", () => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  const toggle = qs("#password-toggle");
  toggle.textContent = showing ? "Show" : "Hide";
  toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
});

function validate() {
  let valid = true;
  if (!identifierInput.value.trim()) {
    setFieldError(identifierInput, "Enter your email or phone number.");
    valid = false;
  } else {
    clearFieldError(identifierInput);
  }
  if (!passwordInput.value) {
    setFieldError(passwordInput, "Enter your password.");
    valid = false;
  } else {
    clearFieldError(passwordInput);
  }
  return valid;
}

identifierInput.addEventListener("input", () => clearFieldError(identifierInput));
passwordInput.addEventListener("input", () => clearFieldError(passwordInput));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.hidden = true;
  if (!validate()) return;

  submitBtn.disabled = true;
  submitSpinner.hidden = false;
  submitLabel.textContent = "Signing in...";

  try {
    const user = await login(identifierInput.value, passwordInput.value);
    window.location.replace(ROLE_HOME[user.role] || "/login.html");
  } catch {
    errorEl.textContent = "Email or password is incorrect.";
    errorEl.hidden = false;
    submitBtn.disabled = false;
    submitSpinner.hidden = true;
    submitLabel.textContent = "Log in";
  }
});
