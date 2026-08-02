import { el } from "./dom.js";
import { TRIP_STATUS_LABELS, INVOICE_STATUS_LABELS, formatDate } from "./format.js";

export function tripStatusBadge(status) {
  const label = TRIP_STATUS_LABELS[status] || status;
  // A pulsing dot marks a trip with a driver in motion or standing at the door:
  // the states where someone is waiting on this exact moment.
  const live = status === "EN_ROUTE" || status === "ARRIVED";
  const children = live ? [el("span", { class: "status-pulse-dot" }), label] : [label];
  return el("span", { class: `trip-status trip-status--${status.toLowerCase()}` }, children);
}

export function invoiceStatusBadge(status) {
  const label = INVOICE_STATUS_LABELS[status] || status;
  return el("span", { class: `invoice-status invoice-status--${status.toLowerCase()}`, text: label });
}

export function licenseBadge(driver) {
  if (!driver.license_expiry_date) return null;
  let cls = "license-badge";
  let text = `License expires ${formatDate(driver.license_expiry_date)}`;
  if (driver.license_expired) {
    cls = "license-badge license-badge--expired";
    text = `License expired ${formatDate(driver.license_expiry_date)}`;
  } else if (driver.license_expiring_soon) {
    cls = "license-badge license-badge--expiring";
  }
  return el("span", { class: cls, text });
}
