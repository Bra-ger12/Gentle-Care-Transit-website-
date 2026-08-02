import { el } from "./dom.js";

/**
 * A destructive action that has to carry an explanation — declining an assignment,
 * reporting a no-show. The trigger reveals a one-line reason; the confirm button
 * stays disabled until something is typed, so the record never gets a blank reason.
 *
 * `onSubmit(reason, button)` is awaited: resolve to accept the action, throw to
 * leave the button re-enabled for another try.
 *
 * Returns a DocumentFragment holding the trigger and its reveal, so it drops into
 * an existing button row without an extra wrapper.
 */
export function reasonAction({ trigger, triggerClass = "btn", placeholder, confirm, onSubmit }) {
  const input = el("input", { type: "text", placeholder, required: "required" });
  const confirmBtn = el("button", { class: triggerClass, type: "button", text: confirm, disabled: "disabled" });

  input.addEventListener("input", () => {
    confirmBtn.disabled = input.value.trim().length === 0;
  });
  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    try {
      await onSubmit(input.value.trim(), confirmBtn);
    } catch {
      confirmBtn.disabled = false;
    }
  });

  const form = el("div", { class: "inline-form collapsible" }, [
    input,
    el("div", { class: "inline-form__actions" }, [confirmBtn]),
  ]);

  const triggerBtn = el("button", {
    class: triggerClass,
    type: "button",
    text: trigger,
    onclick: () => {
      form.classList.toggle("is-open");
      if (form.classList.contains("is-open")) input.focus();
    },
  });

  const fragment = document.createDocumentFragment();
  fragment.append(triggerBtn, form);
  return fragment;
}
