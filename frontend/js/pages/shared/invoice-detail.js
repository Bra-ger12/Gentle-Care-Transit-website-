import { requireRole } from "../../api/auth.js";
import { getInvoice, finalizeInvoice, voidInvoice, markInvoicePaid } from "../../api/billing.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { invoiceStatusBadge } from "../../ui/badges.js";
import { formatCurrency, MOBILITY_LABELS, formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

export async function run(role) {
  const user = await requireRole([role]);
  if (!user) return;
  renderNav(qs("#app-nav"), user);

  const isAdmin = role === "ADMIN";
  const listBase = isAdmin ? "/admin/invoices.html" : "/rider/invoices.html";
  qs("#back-link").href = listBase;

  const id = new URLSearchParams(location.search).get("id");
  const content = qs("#content");

  async function render(invoice) {
    clear(content);
    const detail = el("div", { class: "trip-detail" }, [
      el("p", {}, [invoiceStatusBadge(invoice.status)]),
      el("p", { text: `Rider: ${invoice.rider_name_snapshot}` }),
    ]);
    if (invoice.medicaid_id_snapshot) detail.append(el("p", { text: `Medicaid ID: ${invoice.medicaid_id_snapshot}` }));
    detail.append(
      el("p", { text: `Payer type: ${invoice.payer_type === "MEDICAID" ? "Medicaid" : "Private pay"}` }),
      el("p", {
        text: `Mobility tier: ${invoice.mobility_need_snapshot ? MOBILITY_LABELS[invoice.mobility_need_snapshot] : "Ambulatory (default)"}`,
      }),
      el("p", { text: `Mileage: ${invoice.mileage_snapshot ?? "—"}` }),
      el("p", { text: `Base fare: ${formatCurrency(invoice.base_fare)}` }),
      el("p", {
        text: `Mileage amount: ${formatCurrency(invoice.mileage_amount)} (at ${formatCurrency(invoice.per_mile_rate)}/mile)`,
      }),
      el("p", { text: `Total: ${formatCurrency(invoice.total_amount)}`, style: "font-weight: 600" })
    );
    if (invoice.payment_reference) detail.append(el("p", { text: `Payment reference: ${invoice.payment_reference}` }));
    if (invoice.void_reason) detail.append(el("p", { text: `Void reason: ${invoice.void_reason}` }));

    const timestampParts = [];
    if (invoice.created_at) timestampParts.push(`Created ${formatDateTime(invoice.created_at)}`);
    if (invoice.finalized_at) timestampParts.push(`Finalized ${formatDateTime(invoice.finalized_at)}`);
    if (invoice.paid_at) timestampParts.push(`Paid ${formatDateTime(invoice.paid_at)}`);
    if (invoice.voided_at) timestampParts.push(`Voided ${formatDateTime(invoice.voided_at)}`);
    if (timestampParts.length) detail.append(el("p", { class: "page-status-note", text: timestampParts.join(" · ") }));

    content.append(detail);

    if (!isAdmin) return;

    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const actions = el("div", { class: "dispatch-table__actions" });

    if (invoice.status === "DRAFT") {
      const finalizeBtn = el("button", {
        class: "btn btn--primary",
        text: "Finalize",
        onclick: async () => {
          errorEl.hidden = true;
          finalizeBtn.disabled = true;
          try {
            const updated = await finalizeInvoice(invoice.id);
            render(updated);
            showToast("Invoice finalized.", { type: "success" });
          } catch {
            errorEl.textContent = "Could not finalize this invoice.";
            errorEl.hidden = false;
            finalizeBtn.disabled = false;
          }
        },
      });
      actions.append(finalizeBtn);
    }

    if (invoice.status === "FINALIZED") {
      const revealBtn = el("button", { class: "btn btn--primary", text: "Mark paid" });
      const paidForm = el("div", { class: "inline-form collapsible" });
      const refInput = el("input", { type: "text", placeholder: "Payment reference (optional)" });
      const confirmBtn = el("button", {
        class: "btn btn--primary",
        text: "Confirm paid",
        onclick: async () => {
          errorEl.hidden = true;
          confirmBtn.disabled = true;
          try {
            const updated = await markInvoicePaid(invoice.id, refInput.value || undefined);
            render(updated);
            showToast("Invoice marked paid.", { type: "success" });
          } catch {
            errorEl.textContent = "Could not mark this invoice paid.";
            errorEl.hidden = false;
            confirmBtn.disabled = false;
          }
        },
      });
      paidForm.append(refInput, el("div", { class: "inline-form__actions" }, [confirmBtn]));
      revealBtn.addEventListener("click", () => {
        paidForm.classList.toggle("is-open");
      });
      actions.append(revealBtn);
      content.append(paidForm);
    }

    if (invoice.status === "DRAFT" || invoice.status === "FINALIZED") {
      const revealBtn = el("button", { class: "btn btn--danger", text: "Void invoice" });
      const voidForm = el("div", { class: "inline-form collapsible" });
      const reasonInput = el("input", { type: "text", placeholder: "Reason for voiding", required: "required" });
      const confirmBtn = el("button", { class: "btn btn--danger", text: "Confirm void", disabled: "disabled" });
      reasonInput.addEventListener("input", () => {
        confirmBtn.disabled = reasonInput.value.trim().length === 0;
      });
      confirmBtn.addEventListener("click", async () => {
        errorEl.hidden = true;
        confirmBtn.disabled = true;
        try {
          const updated = await voidInvoice(invoice.id, reasonInput.value);
          render(updated);
          showToast("Invoice voided.", { type: "info" });
        } catch {
          errorEl.textContent = "Could not void this invoice.";
          errorEl.hidden = false;
          confirmBtn.disabled = false;
        }
      });
      voidForm.append(reasonInput, el("div", { class: "inline-form__actions" }, [confirmBtn]));
      revealBtn.addEventListener("click", () => {
        voidForm.classList.toggle("is-open");
      });
      actions.append(revealBtn);
      content.append(voidForm);
    }

    if (actions.childElementCount > 0) content.append(actions);
    content.append(errorEl);
  }

  showLoading(content, "Loading invoice...");
  try {
    const invoice = await getInvoice(id);
    render(invoice);
  } catch {
    showError(content, "Could not load this invoice.");
  }
}
