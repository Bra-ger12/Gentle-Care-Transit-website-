import { apiFetch } from "./client.js";

export const CANCELLABLE_STATUSES = [
  "REQUESTED",
  "CONFIRMED",
  "ASSIGNED",
  "EN_ROUTE",
  "ARRIVED",
  "PICKED_UP",
];

/** Trips that haven't started yet, so they can still be moved to another time. */
export const RESCHEDULABLE_STATUSES = ["REQUESTED", "CONFIRMED", "ASSIGNED"];

// Mirrors SystemSetting.cancellation_cutoff_hours. The server is the authority and
// will refuse a late cancellation regardless; this only decides whether to offer
// the button. Overridden at runtime once the settings summary has loaded.
let cutoffHours = 24;

export function setCancellationCutoffHours(hours) {
  if (Number.isFinite(hours)) cutoffHours = hours;
}

function beforeCutoff(trip) {
  const cutoff = new Date(trip.scheduled_pickup_time).getTime() - cutoffHours * 60 * 60 * 1000;
  return Date.now() < cutoff;
}

export function canCancel(trip) {
  return CANCELLABLE_STATUSES.includes(trip.status) && beforeCutoff(trip);
}

export function canReschedule(trip) {
  return RESCHEDULABLE_STATUSES.includes(trip.status) && beforeCutoff(trip);
}

/** A return leg the rider still has to call in. */
export function awaitingWillCall(trip) {
  return Boolean(trip.is_will_call) && !trip.will_call_requested_at;
}

/** `status` is one code or a comma-separated list; `date` narrows to one day (YYYY-MM-DD). */
export function listTrips(page = 1, status, { date } = {}) {
  const params = new URLSearchParams({ page: String(page) });
  if (status) params.set("status", status);
  if (date) params.set("date", date);
  return apiFetch(`/trips/?${params.toString()}`);
}

/** Today's date in the browser's locale-independent YYYY-MM-DD form, for `listTrips`. */
export function todayParam(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function getTrip(id) {
  return apiFetch(`/trips/${id}/`);
}

export function createTrip(payload) {
  return apiFetch("/trips/", { method: "POST", body: payload });
}

export function cancelTrip(id, reason) {
  return apiFetch(`/trips/${id}/cancel/`, { method: "POST", body: { reason } });
}

export function confirmTrip(id) {
  return apiFetch(`/trips/${id}/confirm/`, { method: "POST" });
}

export function assignTrip(id, driverId) {
  return apiFetch(`/trips/${id}/assign/`, { method: "POST", body: { driver_id: driverId } });
}

export function autoAssignTrip(id) {
  return apiFetch(`/trips/${id}/auto-assign/`, { method: "POST" });
}

export function reassignTrip(id, driverId) {
  return apiFetch(`/trips/${id}/reassign/`, { method: "POST", body: driverId ? { driver_id: driverId } : {} });
}

export function acceptTrip(id) {
  return apiFetch(`/trips/${id}/accept/`, { method: "POST" });
}

export function declineTrip(id, reason) {
  return apiFetch(`/trips/${id}/decline/`, { method: "POST", body: { reason } });
}

export function markEnRoute(id) {
  return apiFetch(`/trips/${id}/en-route/`, { method: "POST" });
}

export function markArrived(id) {
  return apiFetch(`/trips/${id}/arrive/`, { method: "POST" });
}

export function markPickedUp(id) {
  return apiFetch(`/trips/${id}/picked-up/`, { method: "POST" });
}

export function completeTrip(id, payload) {
  return apiFetch(`/trips/${id}/complete/`, { method: "POST", body: payload });
}

export function reportNoShow(id, reason) {
  return apiFetch(`/trips/${id}/no-show/`, { method: "POST", body: { reason } });
}

export function rescheduleTrip(id, scheduledPickupTime, reason = "") {
  return apiFetch(`/trips/${id}/reschedule/`, {
    method: "POST",
    body: { scheduled_pickup_time: scheduledPickupTime, reason },
  });
}

/** Rider has finished their appointment and wants their will-call return now. */
export function requestReturn(id) {
  return apiFetch(`/trips/${id}/request-return/`, { method: "POST" });
}

/** Dispatch's ranked list of who to send, nearest on-duty driver first. */
export function driverSuggestions(id) {
  return apiFetch(`/trips/${id}/driver-suggestions/`);
}

export function rateTrip(id, rating, review = "") {
  return apiFetch(`/trips/${id}/rate/`, { method: "POST", body: { rating, review } });
}

export function listRecurringSeries(page = 1) {
  return apiFetch(`/trips/recurring-series/?page=${page}`);
}

export function createRecurringSeries(payload) {
  return apiFetch("/trips/recurring-series/", { method: "POST", body: payload });
}

export function getRecurringSeries(id) {
  return apiFetch(`/trips/recurring-series/${id}/`);
}

export function deactivateRecurringSeries(id) {
  return apiFetch(`/trips/recurring-series/${id}/deactivate/`, { method: "POST" });
}
