import { apiFetch } from "./client.js";
import { requireRole } from "./auth.js";

export function getMyDriverProfile() {
  return apiFetch("/auth/me/driver-profile/");
}

// Shared guard for driver-facing pages: only DRIVER role may proceed past requireRole,
// but an unapproved driver is bounced to the pending-review screen instead of the portal.
export async function requireApprovedDriver() {
  const user = await requireRole(["DRIVER"]);
  if (!user) return null;
  try {
    const profile = await getMyDriverProfile();
    if (!profile.is_approved) {
      window.location.replace("/driver-pending.html");
      return null;
    }
  } catch {
    // If the profile check itself fails, let the page proceed rather than block on a transient error.
  }
  return user;
}

export function updateMyDriverProfile(payload, isForm = false) {
  return apiFetch("/auth/me/driver-profile/", { method: "PATCH", body: payload, isForm });
}

export function getMyRiderProfile() {
  return apiFetch("/auth/me/rider-profile/");
}

export function updateMyRiderProfile(payload) {
  return apiFetch("/auth/me/rider-profile/", { method: "PATCH", body: payload });
}

export function listDrivers(isApproved, page) {
  const params = new URLSearchParams();
  if (isApproved !== undefined) params.set("is_approved", String(isApproved));
  if (page) params.set("page", String(page));
  const query = params.toString();
  return apiFetch(`/auth/drivers/${query ? `?${query}` : ""}`);
}

/**
 * Every driver across all pages — the dispatch board needs the whole roster for
 * its assign dropdown and its "online now" count, not just the first page.
 * Capped so a bad `next` link can never loop forever.
 */
export async function listAllDrivers(isApproved, maxPages = 10) {
  const first = await listDrivers(isApproved);
  const results = [...first.results];
  let hasNext = Boolean(first.next);
  for (let page = 2; hasNext && page <= maxPages; page += 1) {
    const next = await listDrivers(isApproved, page);
    results.push(...next.results);
    hasNext = Boolean(next.next);
  }
  return { count: first.count, results };
}

/**
 * Approved drivers who are on duty right now, with their last known position
 * and current job.
 *
 * The dispatch board is otherwise assembled from trips, which means a driver
 * who is online but between jobs -- the very person you want to hand the next
 * trip to -- never appeared on it.
 */
export function listOnDutyDrivers() {
  return apiFetch("/auth/drivers/on-duty/");
}

export function getDriver(id) {
  return apiFetch(`/auth/drivers/${id}/`);
}

export function approveDriver(id) {
  return apiFetch(`/auth/drivers/${id}/approve/`, { method: "POST" });
}

export function rejectDriver(id, reason) {
  return apiFetch(`/auth/drivers/${id}/reject/`, { method: "POST", body: { reason } });
}

export function updateDriverVehicle(id, payload) {
  return apiFetch(`/auth/drivers/${id}/vehicle/`, { method: "PATCH", body: payload });
}

// --- Driver calendar ---

export function listAvailability() {
  return apiFetch("/auth/availability/");
}

export function createAvailability(payload) {
  return apiFetch("/auth/availability/", { method: "POST", body: payload });
}

export function deleteAvailability(id) {
  return apiFetch(`/auth/availability/${id}/`, { method: "DELETE" });
}

export function listTimeOff() {
  return apiFetch("/auth/time-off/");
}

export function createTimeOff(payload) {
  return apiFetch("/auth/time-off/", { method: "POST", body: payload });
}

export function deleteTimeOff(id) {
  return apiFetch(`/auth/time-off/${id}/`, { method: "DELETE" });
}

/** Report the driver's position so dispatch can place them and match by proximity. */
export function reportLocation(lat, lng) {
  return apiFetch("/auth/me/location/", { method: "POST", body: { lat, lng } });
}

// --- Admin account management ---

export function listUsers({ role, q, page = 1 } = {}) {
  const params = new URLSearchParams({ page: String(page) });
  if (role) params.set("role", role);
  if (q) params.set("q", q);
  return apiFetch(`/auth/users/?${params.toString()}`);
}

export function suspendUser(id) {
  return apiFetch(`/auth/users/${id}/suspend/`, { method: "POST" });
}

export function activateUser(id) {
  return apiFetch(`/auth/users/${id}/activate/`, { method: "POST" });
}

export function requestPasswordReset(email) {
  return apiFetch("/auth/password-reset/request/", { method: "POST", body: { email }, auth: false });
}

export function confirmPasswordReset(uid, token, newPassword) {
  return apiFetch("/auth/password-reset/confirm/", {
    method: "POST",
    body: { uid, token, new_password: newPassword },
    auth: false,
  });
}
