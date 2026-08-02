import { el, dataTable } from "./dom.js";
import { tripStatusBadge } from "./badges.js";
import { formatDateTime, formatDate, MOBILITY_LABELS } from "./format.js";
import { ratingStars } from "./rating.js";

// Trips a rider/driver can still act on (vs. terminal COMPLETED/CANCELLED/NO_SHOW).
export const ACTIVE_TRIP_STATUSES = [
  "REQUESTED",
  "CONFIRMED",
  "ASSIGNED",
  "EN_ROUTE",
  "ARRIVED",
  "PICKED_UP",
];
// Trips with a live driver location to follow on the map.
export const LIVE_TRIP_STATUSES = ["EN_ROUTE", "ARRIVED", "PICKED_UP"];

const DAY = 1440;

/** Friendly countdown/relative label, e.g. "in 3 days", "in 2 hr", "20 min ago". */
export function relativeWhen(iso) {
  const diffMin = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  const abs = Math.abs(diffMin);
  let phrase;
  if (abs < 1) return "now";
  if (abs < 60) phrase = `${abs} min`;
  else if (abs < DAY) phrase = `${Math.round(abs / 60)} hr`;
  else {
    const days = Math.round(abs / DAY);
    phrase = `${days} day${days > 1 ? "s" : ""}`;
  }
  return diffMin < 0 ? `${phrase} ago` : `in ${phrase}`;
}

/** A row of call-to-action buttons: [{ label, href, primary }]. */
export function actionRow(actions) {
  return el(
    "div",
    { class: "dash-actions" },
    actions.map((a) =>
      el("a", { class: `btn ${a.primary ? "btn--primary" : ""}`.trim(), href: a.href, text: a.label })
    )
  );
}

/** A responsive grid of stat tiles: [{ label, value, hint, accent }]. */
export function statCards(cards) {
  return el(
    "div",
    { class: "kpi-grid dash-stats" },
    cards.map((c) =>
      el("div", { class: `kpi-tile${c.accent ? " kpi-tile--accent" : ""}` }, [
        el("p", { class: "kpi-tile__label", text: c.label }),
        el("p", { class: "kpi-tile__value", text: String(c.value) }),
        c.hint ? el("p", { class: "kpi-tile__hint", text: c.hint }) : null,
      ])
    )
  );
}

/** The prominent "up next / next assignment" card for the soonest active trip. */
export function featuredTrip(trip, { detailBase, role }) {
  const isLive = LIVE_TRIP_STATUSES.includes(trip.status);
  const needsAction = role === "DRIVER" && trip.status === "ASSIGNED";
  const eyebrow = role === "DRIVER" ? "Your next trip" : "Up next";
  const cta = isLive
    ? role === "DRIVER"
      ? "Open trip"
      : "Track live"
    : needsAction
      ? "Accept / start"
      : "View trip";

  return el("div", { class: `feature-trip${needsAction ? " feature-trip--action" : ""}` }, [
    el("div", { class: "feature-trip__head" }, [
      el("span", { class: "feature-trip__eyebrow", text: eyebrow }),
      tripStatusBadge(trip.status),
    ]),
    el("div", { class: "feature-trip__when-row" }, [
      el("span", { class: "feature-trip__when", text: formatDateTime(trip.scheduled_pickup_time) }),
      el("span", { class: "feature-trip__countdown", text: relativeWhen(trip.scheduled_pickup_time) }),
    ]),
    el("p", { class: "feature-trip__route", text: `${trip.pickup_address} → ${trip.dropoff_address}` }),
    el("a", { class: "btn btn--primary feature-trip__cta", href: `${detailBase}?id=${trip.id}`, text: cta }),
  ]);
}

/** The shared trip list used on both dashboards. */
export function tripTimeline(trips, detailBase) {
  return el(
    "ul",
    { class: "trip-timeline" },
    trips.map((trip) =>
      el("li", { class: "trip-timeline__item" }, [
        el("a", { class: "trip-timeline__link", href: `${detailBase}?id=${trip.id}` }, [
          el("div", { class: "trip-timeline__row" }, [
            el("span", { text: formatDateTime(trip.scheduled_pickup_time) }),
            tripStatusBadge(trip.status),
          ]),
          el("div", {
            class: "trip-timeline__addresses",
            text: `${trip.pickup_address} → ${trip.dropoff_address}`,
          }),
        ]),
      ])
    )
  );
}

/** Count of trips in `results` scheduled for today (client-local). */
export function countToday(results) {
  const today = new Date().toDateString();
  return results.filter((t) => new Date(t.scheduled_pickup_time).toDateString() === today).length;
}

function timeOnly(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/**
 * One labelled line — icon · caption · value (· optional trailing control) — the
 * row shape the driver's active-trip panel and trip record are both built from.
 */
export function labelledRow(icon, label, value, trailing) {
  return el("div", { class: "ops-row" }, [
    el("span", { class: "ops-row__icon", text: icon, "aria-hidden": "true" }),
    el("span", { class: "ops-row__label", text: label }),
    el("span", { class: "ops-row__value" }, [value instanceof Node ? value : el("span", { text: String(value) })]),
    trailing || null,
  ]);
}

/** A bordered group of `labelledRow`s. */
export function labelledRows(rows) {
  return el("div", { class: "ops-rows" }, rows);
}

/** One leg of a route: a coloured dot, a label and the address. */
export function routeLeg(kind, label, address) {
  return el("div", { class: "route-leg" }, [
    el("span", { class: `route-leg__dot route-leg__dot--${kind}` }),
    el("div", { class: "route-leg__body" }, [
      el("span", { class: "route-leg__label", text: label }),
      el("span", { class: "route-leg__address", text: address }),
    ]),
  ]);
}

/**
 * The patient hub's "Your Next Ride" card. `trip` must be the *detail* payload —
 * the driver's rating/plate/vehicle come from `TripDetailSerializer` only.
 * `cancel` is `{ enabled, onCancel }`; when disabled the 24-hour cutoff note shows.
 */
export function nextRideCard(trip, { detailBase, cancel = {} }) {
  const isLive = LIVE_TRIP_STATUSES.includes(trip.status);
  const driverName = trip.assigned_driver_name;

  const chips = el("div", { class: "next-ride__chips" }, [
    tripStatusBadge(trip.status),
    trip.mobility_need
      ? el("span", { class: "chip", text: MOBILITY_LABELS[trip.mobility_need] || trip.mobility_need })
      : null,
  ]);

  const driverRow = driverName
    ? el("div", { class: "next-ride__driver" }, [
        el("div", { class: "next-ride__driver-id" }, [
          el("span", { class: "next-ride__driver-name", text: driverName }),
          trip.assigned_driver_rating != null ? ratingStars(trip.assigned_driver_rating) : null,
        ]),
        el("span", {
          class: "next-ride__vehicle",
          text: [trip.assigned_driver_vehicle_type, trip.assigned_driver_vehicle_plate]
            .filter(Boolean)
            .join(" · ") || "Vehicle details to follow",
        }),
      ])
    : el("p", { class: "next-ride__driver-pending", text: "Dispatch is assigning your driver." });

  const actions = el("div", { class: "next-ride__actions" }, [
    el("a", {
      class: "btn btn--primary",
      href: `${detailBase}?id=${trip.id}`,
      text: isLive ? "Track driver live" : "View ride details",
    }),
  ]);
  if (cancel.enabled) {
    actions.append(el("button", { class: "btn btn--danger", text: "Cancel ride", onclick: cancel.onCancel }));
  }

  const card = el("section", { class: `next-ride${isLive ? " next-ride--live" : ""}` }, [
    el("div", { class: "next-ride__head" }, [
      el("span", { class: "next-ride__eyebrow", text: "Your next ride" }),
      chips,
    ]),
    el("div", { class: "next-ride__when" }, [
      el("span", { class: "next-ride__date", text: formatDate(trip.scheduled_pickup_time) }),
      el("span", { class: "next-ride__time", text: timeOnly(trip.scheduled_pickup_time) }),
      el("span", { class: "next-ride__countdown", text: relativeWhen(trip.scheduled_pickup_time) }),
    ]),
    el("div", { class: "next-ride__route" }, [
      routeLeg("pickup", "Pickup", trip.pickup_address),
      routeLeg("dropoff", "Destination", trip.dropoff_address),
    ]),
    driverRow,
    actions,
  ]);
  if (!cancel.enabled && cancel.note) {
    card.append(el("p", { class: "next-ride__note", text: cancel.note }));
  }
  return card;
}

/**
 * Distinct destinations from a rider's own past trips, most recent first.
 * Real history — the backend has no saved-locations model.
 */
export function recentDestinations(trips, limit = 4) {
  const seen = new Map();
  for (const trip of trips) {
    if (!trip.dropoff_address) continue;
    const entry = seen.get(trip.dropoff_address);
    if (entry) entry.count += 1;
    else seen.set(trip.dropoff_address, { address: trip.dropoff_address, count: 1, last: trip.scheduled_pickup_time });
  }
  return [...seen.values()].slice(0, limit);
}

/** "Quick booking" cards, each re-booking a previously used destination. */
export function locationCards(destinations, bookBase = "/rider/book.html") {
  return el(
    "div",
    { class: "quick-book" },
    destinations.map((dest) =>
      el("article", { class: "quick-book__card" }, [
        el("p", { class: "quick-book__address", text: dest.address }),
        el("p", {
          class: "quick-book__meta",
          text: `${dest.count} previous trip${dest.count === 1 ? "" : "s"} · last ${formatDate(dest.last)}`,
        }),
        el("a", {
          class: "btn quick-book__cta",
          href: `${bookBase}?dropoff=${encodeURIComponent(dest.address)}`,
          text: "Book from here",
        }),
      ])
    )
  );
}

/** Compact trips table (Date · Time · Destination · Status) for the patient hub. */
export function tripsTable(trips, detailBase) {
  const rows = trips.map((trip) =>
    el("tr", { class: "dispatch-table__row" }, [
      el("td", { text: formatDate(trip.scheduled_pickup_time) }),
      el("td", { class: "mono", text: timeOnly(trip.scheduled_pickup_time) }),
      el("td", {}, [el("a", { href: `${detailBase}?id=${trip.id}`, text: trip.dropoff_address })]),
      el("td", {}, [tripStatusBadge(trip.status)]),
    ])
  );
  return dataTable(["Date", "Time", "Destination", "Status"], rows);
}
