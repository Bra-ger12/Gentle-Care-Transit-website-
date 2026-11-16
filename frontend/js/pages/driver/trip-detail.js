import { requireApprovedDriver } from "../../api/drivers.js";
import { getTrip, acceptTrip, declineTrip, markEnRoute, markPickedUp, reportNoShow } from "../../api/trips.js";
import { openSocket } from "../../api/realtime.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { tripStatusBadge } from "../../ui/badges.js";
import { ratingStars } from "../../ui/rating.js";
import { labelledRow, labelledRows, LIVE_TRIP_STATUSES } from "../../ui/dashboard.js";
import { reasonAction } from "../../ui/reason-action.js";
import { formatCurrency, MOBILITY_LABELS, formatDateTime } from "../../ui/format.js";
import { tripCompletionForm } from "../shared/trip-completion-form.js";
import { showToast } from "../../ui/toast.js";

// The trip's own history, in the order it happens.
const MILESTONES = [
  ["assigned_at", "Assigned to you"],
  ["accepted_at", "You accepted"],
  ["en_route_at", "En route"],
  ["picked_up_at", "Passenger boarded"],
  ["completed_at", "Completed"],
  ["no_show_at", "Reported no-show"],
  ["cancelled_at", "Cancelled"],
];

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);
  const id = new URLSearchParams(location.search).get("id");
  const content = qs("#content");

  let streamer = null;
  function stopStreaming() {
    if (streamer) {
      streamer.close();
      streamer = null;
    }
  }
  window.addEventListener("beforeunload", stopStreaming);

  const reload = async () => {
    try {
      render(await getTrip(id));
    } catch {
      showError(content, "Could not reload this trip.");
    }
  };

  async function runAction(button, errorEl, fn, successMessage) {
    button.disabled = true;
    errorEl.hidden = true;
    try {
      const updated = await fn();
      render(updated);
      showToast(successMessage, { type: "success" });
    } catch (error) {
      errorEl.textContent = "Could not update this trip. Try again, or call dispatch.";
      errorEl.hidden = false;
      button.disabled = false;
      throw error; // lets reasonAction keep its confirm button usable
    }
  }

  function render(trip) {
    stopStreaming();
    clear(content);

    content.append(
      el("div", { class: "record__head" }, [
        el("h1", { class: "record__title", text: trip.rider_name || "Trip record" }),
        tripStatusBadge(trip.status),
      ]),
      passengerRows(trip),
      timeline(trip)
    );

    if (trip.notes) {
      content.append(
        el("p", { class: "ops-notes" }, [
          el("span", { class: "ops-notes__icon", text: "⚠️" }),
          el("span", {}, [el("strong", { text: "Note: " }), trip.notes]),
        ])
      );
    }
    if (trip.cancellation_reason) {
      content.append(el("p", { class: "record__reason", text: `Cancellation reason: ${trip.cancellation_reason}` }));
    }
    if (trip.no_show_reason) {
      content.append(el("p", { class: "record__reason", text: `No-show reason: ${trip.no_show_reason}` }));
    }
    if (trip.decline_reason) {
      content.append(el("p", { class: "record__reason", text: `Decline reason: ${trip.decline_reason}` }));
    }

    if (trip.status === "COMPLETED") content.append(completionRecord(trip), feedback(trip));
    if (LIVE_TRIP_STATUSES.includes(trip.status)) content.append(startStreaming(trip));

    content.append(actions(trip));
  }

  function passengerRows(trip) {
    const needs = trip.rider_mobility_needs || [];
    return labelledRows([
      labelledRow(
        "👤",
        "Passenger",
        el("span", { text: trip.rider_name || "—" }),
        trip.rider_phone
          ? el("a", { class: "btn ops-row__action", href: `tel:${trip.rider_phone}`, text: "Call" })
          : null
      ),
      labelledRow("♿", "Needs", needs.length > 0 ? needs.map((n) => MOBILITY_LABELS[n] || n).join(" / ") : "None recorded"),
      labelledRow("📍", "Pickup", trip.pickup_address),
      labelledRow("🏁", "Dropoff", trip.dropoff_address),
      labelledRow("⏱️", "Scheduled pickup", formatDateTime(trip.scheduled_pickup_time)),
      labelledRow("🛣️", "Booked mileage", trip.mileage ? `${Number(trip.mileage).toFixed(1)} mi` : "—"),
      labelledRow("💵", "Estimated fare", formatCurrency(trip.total_cost)),
      labelledRow("🚐", "Driver", trip.assigned_driver_name || "Unassigned"),
    ]);
  }

  /** Every milestone the trip actually reached, with its timestamp. */
  function timeline(trip) {
    const reached = MILESTONES.filter(([field]) => trip[field]);
    if (reached.length === 0) return el("p", { class: "ops-panel__note", text: "No milestones recorded yet." });
    return el("section", { class: "record__section" }, [
      el("p", { class: "ops-workflow__label", text: "Trip history" }),
      el(
        "ul",
        { class: "record__timeline" },
        reached.map(([field, label]) =>
          el("li", {}, [
            el("span", { class: "record__timeline-label", text: label }),
            el("span", { class: "record__timeline-time mono", text: formatDateTime(trip[field]) }),
          ])
        )
      ),
    ]);
  }

  /** What you attested to at drop-off — the record behind the invoice. */
  function completionRecord(trip) {
    const driven =
      trip.odometer_start != null && trip.odometer_end != null
        ? `${Number(trip.odometer_end) - Number(trip.odometer_start)} mi (${trip.odometer_start} → ${trip.odometer_end})`
        : "—";
    return el("section", { class: "record__section" }, [
      el("p", { class: "ops-workflow__label", text: "Completion record" }),
      labelledRows([
        labelledRow("🧾", "Odometer", driven),
        labelledRow("✍️", "Attested by", trip.completion_attestation || "—"),
      ]),
    ]);
  }

  /** The rider's rating of this trip, once they've left one. */
  function feedback(trip) {
    const section = el("section", { class: "record__section" }, [
      el("p", { class: "ops-workflow__label", text: "Passenger feedback" }),
    ]);
    if (!trip.rating) {
      section.append(el("p", { class: "ops-panel__note", text: "This passenger hasn't rated the ride yet." }));
      return section;
    }
    section.append(el("p", {}, [ratingStars(trip.rating)]));
    if (trip.review) section.append(el("p", { class: "rating-review", text: `“${trip.review}”` }));
    if (trip.rated_at) {
      section.append(el("p", { class: "ops-panel__note", text: `Rated ${formatDateTime(trip.rated_at)}` }));
    }
    return section;
  }

  /**
   * The same transitions the board offers, so a driver arriving here from a
   * notification link can work the trip without bouncing to the dashboard.
   */
  function actions(trip) {
    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const row = el("div", { class: "ops-workflow__accept" });

    if (trip.status === "ASSIGNED" && !trip.accepted_at) {
      const accept = el("button", { class: "btn btn--primary", text: "Accept this assignment" });
      accept.addEventListener("click", () =>
        runAction(accept, errorEl, () => acceptTrip(trip.id), "Trip accepted.").catch(() => {})
      );
      row.append(
        accept,
        reasonAction({
          trigger: "Decline",
          placeholder: "Why you can't take this trip (dispatch sees this)",
          confirm: "Confirm decline",
          onSubmit: (reason, button) =>
            runAction(button, errorEl, () => declineTrip(trip.id, reason), "Trip declined."),
        })
      );
    } else if (trip.status === "ASSIGNED") {
      const start = el("button", { class: "btn btn--primary", text: "En route to pickup" });
      start.addEventListener("click", () =>
        runAction(start, errorEl, () => markEnRoute(trip.id), "You're en route.").catch(() => {})
      );
      row.append(start);
    } else if (trip.status === "EN_ROUTE") {
      const boarded = el("button", { class: "btn btn--primary", text: "Passenger boarded" });
      boarded.addEventListener("click", () =>
        runAction(boarded, errorEl, () => markPickedUp(trip.id), "Passenger picked up.").catch(() => {})
      );
      row.append(
        boarded,
        reasonAction({
          trigger: "Report no-show",
          triggerClass: "btn btn--danger",
          placeholder: "What happened at the pickup?",
          confirm: "Confirm no-show",
          onSubmit: (reason, button) =>
            runAction(button, errorEl, () => reportNoShow(trip.id, reason), "No-show reported."),
        })
      );
    }

    const wrap = el("section", { class: "record__section" });
    if (row.childElementCount > 0) wrap.append(row);
    if (trip.status === "PICKED_UP") {
      wrap.append(
        el("p", { class: "ops-workflow__label", text: "Complete the trip" }),
        tripCompletionForm(trip.id, reload)
      );
    }
    wrap.append(errorEl, el("a", { class: "ops-workflow__link", href: "/driver/index.html", text: "← Back to today's board" }));
    return wrap;
  }

  // Keep sharing location if the driver works the trip from this page.
  function startStreaming(trip) {
    const text = el("span", { class: "geo-pill__text", text: "Sharing your location with the passenger…" });
    const pill = el("div", { class: "geo-pill" }, [el("span", { class: "geo-pill__dot" }), text]);
    const socket = openSocket(`trips/${trip.id}/track/`);
    let watchId = null;

    if ("geolocation" in navigator) {
      watchId = navigator.geolocation.watchPosition(
        (pos) => socket.send({ type: "location", lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => {
          text.textContent = "Location sharing is blocked — enable location so the passenger can track you.";
          pill.classList.add("geo-pill--error");
        },
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 }
      );
    } else {
      text.textContent = "This device can't share location.";
      pill.classList.add("geo-pill--error");
    }

    streamer = {
      close: () => {
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        socket.close();
      },
    };
    return pill;
  }

  showLoading(content, "Loading trip...");
  try {
    render(await getTrip(id));
  } catch {
    showError(content, "Could not load this trip.");
  }
}
