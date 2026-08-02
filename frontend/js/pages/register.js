import { register, login, ROLE_HOME } from "../api/auth.js";
import { qs, el, clear } from "../ui/dom.js";
import { setFieldError, clearFieldError } from "../ui/validation.js";
import { initPasswordStrength } from "../ui/password-strength.js";

const form = qs("#register-form");
const submitBtn = qs("#submit-btn");
const submitSpinner = qs("#submit-spinner");
const submitLabel = qs("#submit-label");
const errorEl = qs("#error");

const firstNameInput = qs("#first_name");
const lastNameInput = qs("#last_name");
const emailInput = qs("#email");
const passwordInput = qs("#password");
const confirmPasswordInput = qs("#confirm_password");
const termsCheckbox = qs("#terms");
const driverNote = qs("#driver-note");

qs("#password-toggle").addEventListener("click", () => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  confirmPasswordInput.type = showing ? "password" : "text";
  const toggle = qs("#password-toggle");
  toggle.textContent = showing ? "Show" : "Hide";
  toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
});

for (const radio of form.querySelectorAll('input[name="role"]')) {
  radio.addEventListener("change", () => {
    driverNote.hidden = radio.value !== "DRIVER";
  });
}

initPasswordStrength(passwordInput, qs("#password-strength"), qs("#password-strength-label"));
passwordInput.addEventListener("input", () => clearFieldError(passwordInput));

confirmPasswordInput.addEventListener("input", () => clearFieldError(confirmPasswordInput));
termsCheckbox.addEventListener("change", () => clearFieldError(termsCheckbox));
for (const input of [firstNameInput, lastNameInput, emailInput]) {
  input.addEventListener("input", () => clearFieldError(input));
}

function renderServerErrors(data) {
  clear(errorEl);
  if (data && typeof data === "object") {
    const items = Object.entries(data).map(([field, messages]) =>
      el("li", { text: `${field}: ${Array.isArray(messages) ? messages.join(" ") : messages}` })
    );
    if (items.length) {
      errorEl.append(el("ul", {}, items));
      errorEl.hidden = false;
      return;
    }
  }
  errorEl.textContent = "Registration failed.";
  errorEl.hidden = false;
}

function validate() {
  let valid = true;
  if (!firstNameInput.value.trim()) {
    setFieldError(firstNameInput, "Enter your first name.");
    valid = false;
  } else clearFieldError(firstNameInput);

  if (!lastNameInput.value.trim()) {
    setFieldError(lastNameInput, "Enter your last name.");
    valid = false;
  } else clearFieldError(lastNameInput);

  if (!emailInput.value.trim()) {
    setFieldError(emailInput, "Enter your email address.");
    valid = false;
  } else clearFieldError(emailInput);

  if (!passwordInput.value || passwordInput.value.length < 8) {
    setFieldError(passwordInput, "Password must be at least 8 characters.");
    valid = false;
  } else clearFieldError(passwordInput);

  if (confirmPasswordInput.value !== passwordInput.value) {
    setFieldError(confirmPasswordInput, "Passwords do not match.");
    valid = false;
  } else clearFieldError(confirmPasswordInput);

  if (!termsCheckbox.checked) {
    setFieldError(termsCheckbox, "You must agree to continue.");
    valid = false;
  } else clearFieldError(termsCheckbox);

  return valid;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.hidden = true;
  clear(errorEl);
  if (!validate()) return;

  submitBtn.disabled = true;
  submitSpinner.hidden = false;
  submitLabel.textContent = "Registering...";

  const email = emailInput.value;
  const password = passwordInput.value;
  const payload = {
    first_name: firstNameInput.value,
    last_name: lastNameInput.value,
    email,
    phone_number: qs("#phone_number").value || undefined,
    password,
    role: form.querySelector('input[name="role"]:checked').value,
  };

  try {
    await register(payload);
    const user = await login(email, password);
    window.location.replace(ROLE_HOME[user.role] || "/login.html");
  } catch (err) {
    renderServerErrors(err.data);
    submitBtn.disabled = false;
    submitSpinner.hidden = true;
    submitLabel.textContent = "Register";
  }
});
