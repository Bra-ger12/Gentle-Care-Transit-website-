import { apiFetch, apiFetchBlob } from "./client.js";

export function listRateSchedules() {
  return apiFetch("/billing/rate-schedules/");
}

export function createRateSchedule(payload) {
  return apiFetch("/billing/rate-schedules/", { method: "POST", body: payload });
}

export function updateRateSchedule(id, payload) {
  return apiFetch(`/billing/rate-schedules/${id}/`, { method: "PATCH", body: payload });
}

export function deleteRateSchedule(id) {
  return apiFetch(`/billing/rate-schedules/${id}/`, { method: "DELETE" });
}

export function listInvoices(page = 1) {
  return apiFetch(`/billing/invoices/?page=${page}`);
}

export function getInvoice(id) {
  return apiFetch(`/billing/invoices/${id}/`);
}

export function generateInvoices(tripId) {
  return apiFetch("/billing/invoices/generate/", { method: "POST", body: { trip_id: tripId } });
}

export function finalizeInvoice(id) {
  return apiFetch(`/billing/invoices/${id}/finalize/`, { method: "POST" });
}

export function voidInvoice(id, reason) {
  return apiFetch(`/billing/invoices/${id}/void/`, { method: "POST", body: { reason } });
}

export function markInvoicePaid(id, paymentReference) {
  return apiFetch(`/billing/invoices/${id}/mark-paid/`, {
    method: "POST",
    body: { payment_reference: paymentReference },
  });
}

// NOTE: the query param is always `export_format`, never `format` — DRF reserves the
// literal `format` query key for its own content-negotiation override and will 404
// the request before this view ever runs if that name is used instead.
export async function downloadMedicaidExport(dateFrom, dateTo, exportFormat) {
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, export_format: exportFormat });
  const blob = await apiFetchBlob(`/billing/medicaid-export/?${params.toString()}`);
  return { blob, filename: `medicaid_export_${dateFrom}_${dateTo}.${exportFormat}` };
}
