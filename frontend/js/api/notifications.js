import { apiFetch } from "./client.js";

export function listNotifications({ unreadOnly = false } = {}) {
  return apiFetch(`/notifications/${unreadOnly ? "?unread=true" : ""}`);
}

export function getUnreadCount() {
  return apiFetch("/notifications/unread-count/");
}

export function markNotificationRead(id) {
  return apiFetch(`/notifications/${id}/mark-read/`, { method: "POST" });
}

export function markAllNotificationsRead() {
  return apiFetch("/notifications/mark-all-read/", { method: "POST" });
}

export function getNotificationPreferences() {
  return apiFetch("/notifications/preferences/");
}

export function updateNotificationPreferences(payload) {
  return apiFetch("/notifications/preferences/", { method: "PATCH", body: payload });
}
