import { apiFetch } from "./client.js";
import { setCancellationCutoffHours } from "./trips.js";

/** Operator policy: where the service runs and the rules it runs by. */

export function getSettings() {
  return apiFetch("/operations/settings/");
}

export function updateSettings(payload) {
  return apiFetch("/operations/settings/", { method: "PATCH", body: payload });
}

export function listServiceAreas() {
  return apiFetch("/operations/service-areas/");
}

export function createServiceArea(payload) {
  return apiFetch("/operations/service-areas/", { method: "POST", body: payload });
}

export function updateServiceArea(id, payload) {
  return apiFetch(`/operations/service-areas/${id}/`, { method: "PATCH", body: payload });
}

export function deleteServiceArea(id) {
  return apiFetch(`/operations/service-areas/${id}/`, { method: "DELETE" });
}

/** Towns a PLACE rule may name — also what the booking form lists as recognised. */
export function listPlaces() {
  return apiFetch("/operations/places/");
}

/**
 * The rules any signed-in user is allowed to know: where we run, and the
 * cutoffs their buttons depend on.
 *
 * Reading this also teaches the trips module the real cancellation cutoff, so a
 * "Cancel" button isn't offered for a trip the server will refuse to cancel.
 * Never rejects: a policy lookup failing must not take a dashboard down with it.
 */
export async function loadServiceAreaSummary() {
  try {
    const summary = await apiFetch("/operations/service-area-summary/");
    setCancellationCutoffHours(summary.cancellation_cutoff_hours);
    return summary;
  } catch {
    return null;
  }
}
