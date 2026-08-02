import { requestPasswordReset } from "../api/drivers.js";
import { qs } from "../ui/dom.js";
import { setFieldError, clearFieldError } from "../ui/validation.js";

const form = qs("#forgot-form");
const submitBtn = qs("#submit-btn");
const submitSpinner = qs("#submit-spinner");
const submitLabel = qs("#submit-label");
const emailInput = qs("#email");

emailInput.addEventListener("input", () => clearFieldError(emailInput));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!emailInput.value.trim()) {
    setFieldError(emailInput, "Enter your email address.");
    return;
  }

  submitBtn.disabled = true;
  submitSpinner.hidden = false;
  submitLabel.textContent = "Sending...";

  try {
    await requestPasswordReset(emailInput.value);
  } catch {
    // The backend always returns 200 for this endpoint regardless of whether the
    // email exists, so a network/server error here is the only real failure case —
    // still show the same non-committal confirmation to avoid leaking account existence.
  }
  form.hidden = true;
  qs("#intro").hidden = true;
  qs("#confirmation").hidden = false;
});
