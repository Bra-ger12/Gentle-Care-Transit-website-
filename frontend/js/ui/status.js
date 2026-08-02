import { el, clear } from "./dom.js";

export function showLoading(container, label) {
  clear(container);
  container.append(el("div", { class: "page-status", text: label }));
}

export function showError(container, message) {
  clear(container);
  container.append(el("div", { class: "page-status", text: message }));
}

export function showEmpty(container, message, action) {
  container.append(el("p", { class: "empty-state", text: message }));
  if (action) {
    container.append(el("a", { class: "btn btn--primary empty-state__action", href: action.href, text: action.label }));
  }
}
