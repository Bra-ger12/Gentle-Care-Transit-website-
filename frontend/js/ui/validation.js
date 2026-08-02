import { el } from "./dom.js";

function errorId(input) {
  return `${input.id}-error`;
}

export function setFieldError(input, message) {
  input.classList.add("field--invalid");
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", errorId(input));
  let msgEl = document.getElementById(errorId(input));
  if (!msgEl) {
    msgEl = el("p", { class: "field-error", id: errorId(input), "aria-live": "polite" });
    // If the input is wrapped (e.g. password show/hide toggle), anchor after the wrapper, not the bare input.
    const anchor = input.parentElement?.classList.contains("field-with-action") ? input.parentElement : input;
    anchor.insertAdjacentElement("afterend", msgEl);
  }
  msgEl.textContent = message;
}

export function clearFieldError(input) {
  input.classList.remove("field--invalid");
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-describedby");
  const msgEl = document.getElementById(errorId(input));
  if (msgEl) msgEl.remove();
}
