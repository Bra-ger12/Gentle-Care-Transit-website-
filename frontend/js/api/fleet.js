import { apiFetch } from "./client.js";

/** The DVIR checklist, served by the backend so the form never hard-codes it. */
export function getInspectionChecklist() {
  return apiFetch("/fleet/inspection-checklist/");
}

/** What the signed-in driver has filed today (pre-trip / post-trip). */
export function getTodaysInspections() {
  return apiFetch("/fleet/inspections/today/");
}

export function listInspections({ page, date, needsAttention } = {}) {
  const params = new URLSearchParams();
  if (page) params.set("page", String(page));
  if (date) params.set("date", date);
  if (needsAttention) params.set("needs_attention", "true");
  const query = params.toString();
  return apiFetch(`/fleet/inspections/${query ? `?${query}` : ""}`);
}

export function submitInspection(payload) {
  return apiFetch("/fleet/inspections/", { method: "POST", body: payload });
}

export function reviewInspection(id, resolutionNotes = "") {
  return apiFetch(`/fleet/inspections/${id}/review/`, {
    method: "POST",
    body: { resolution_notes: resolutionNotes },
  });
}
