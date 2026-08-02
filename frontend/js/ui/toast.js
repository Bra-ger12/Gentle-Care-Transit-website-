import { el } from "./dom.js";

let stack = null;

function getStack() {
  if (!stack || !document.body.contains(stack)) {
    stack = el("div", { class: "toast-stack", "aria-live": "polite", "aria-atomic": "true" });
    document.body.append(stack);
  }
  return stack;
}

export function showToast(message, { type = "info" } = {}) {
  const container = getStack();
  const toast = el("div", { class: `toast toast--${type}`, text: message });
  container.append(toast);
  setTimeout(() => {
    toast.classList.add("toast--leaving");
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}
