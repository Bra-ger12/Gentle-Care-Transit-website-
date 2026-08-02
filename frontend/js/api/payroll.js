import { apiFetch } from "./client.js";

function rangeParams({ page, dateFrom, dateTo, unpaid, driver } = {}) {
  const params = new URLSearchParams();
  if (page) params.set("page", String(page));
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (unpaid) params.set("unpaid", "true");
  if (driver) params.set("driver", String(driver));
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** Drivers see their own earnings; admins see everyone's. */
export function listEarnings(options = {}) {
  return apiFetch(`/payroll/earnings/${rangeParams(options)}`);
}

/** Totals for the signed-in driver, or for `driver` when an admin asks. */
export function getEarningsSummary(options = {}) {
  return apiFetch(`/payroll/earnings-summary/${rangeParams(options)}`);
}

export function generateEarnings() {
  return apiFetch("/payroll/earnings/generate/", { method: "POST" });
}

export function markEarningPaid(id, paymentReference = "") {
  return apiFetch(`/payroll/earnings/${id}/mark-paid/`, {
    method: "POST",
    body: { payment_reference: paymentReference },
  });
}

export function listPayRates() {
  return apiFetch("/payroll/pay-rates/");
}

export function createPayRate(payload) {
  return apiFetch("/payroll/pay-rates/", { method: "POST", body: payload });
}

export function updatePayRate(id, payload) {
  return apiFetch(`/payroll/pay-rates/${id}/`, { method: "PATCH", body: payload });
}
