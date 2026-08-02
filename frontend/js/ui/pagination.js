import { el, clear } from "./dom.js";

export function renderPagination(container, { next, previous }, onPrev, onNext) {
  clear(container);
  if (!next && !previous) return;
  const prevBtn = el("button", {
    class: "btn",
    text: "Previous",
    disabled: previous ? undefined : "disabled",
    onclick: () => onPrev(),
  });
  const nextBtn = el("button", {
    class: "btn",
    text: "Next",
    disabled: next ? undefined : "disabled",
    onclick: () => onNext(),
  });
  container.append(el("div", { class: "pagination" }, [prevBtn, nextBtn]));
}
