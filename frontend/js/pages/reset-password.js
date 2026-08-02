import { confirmPasswordReset } from "../api/drivers.js";
import { qs } from "../ui/dom.js";
import { setFieldError, clearFieldError } from "../ui/validation.js";
import { initPasswordStrength } from "../ui/password-strength.js";

const params = new URLSearchParams(location.search);
const uid = params.get("uid");
const token = params.get("token");

if (!uid || !token) {
  qs("#reset-form").hidden = true;
  qs("#missing-link").hidden = false;
} else {
  const form = qs("#reset-form");
  const submitBtn = qs("#submit-btn");
  const submitSpinner = qs("#submit-spinner");
  const submitLabel = qs("#submit-label");
  const errorEl = qs("#error");
  const newPasswordInput = qs("#new_password");
  const confirmPasswordInput = qs("#confirm_password");

  qs("#password-toggle").addEventListener("click", () => {
    const showing = newPasswordInput.type === "text";
    newPasswordInput.type = showing ? "password" : "text";
    confirmPasswordInput.type = showing ? "password" : "text";
    const toggle = qs("#password-toggle");
    toggle.textContent = showing ? "Show" : "Hide";
    toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  });

  initPasswordStrength(newPasswordInput, qs("#password-strength"), qs("#password-strength-label"));
  newPasswordInput.addEventListener("input", () => clearFieldError(newPasswordInput));
  confirmPasswordInput.addEventListener("input", () => clearFieldError(confirmPasswordInput));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;

    let valid = true;
    if (!newPasswordInput.value || newPasswordInput.value.length < 8) {
      setFieldError(newPasswordInput, "Password must be at least 8 characters.");
      valid = false;
    } else clearFieldError(newPasswordInput);
    if (confirmPasswordInput.value !== newPasswordInput.value) {
      setFieldError(confirmPasswordInput, "Passwords do not match.");
      valid = false;
    } else clearFieldError(confirmPasswordInput);
    if (!valid) return;

    submitBtn.disabled = true;
    submitSpinner.hidden = false;
    submitLabel.textContent = "Resetting...";

    try {
      await confirmPasswordReset(uid, token, newPasswordInput.value);
      form.hidden = true;
      qs("#confirmation").hidden = false;
    } catch (err) {
      errorEl.textContent =
        err.data?.detail || "This reset link is invalid or has expired. Request a new one.";
      errorEl.hidden = false;
      submitBtn.disabled = false;
      submitSpinner.hidden = true;
      submitLabel.textContent = "Reset password";
    }
  });
}
