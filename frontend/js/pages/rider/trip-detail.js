import { requireRole } from "../../api/auth.js";
import {
  getTrip,
  cancelTrip,
  rateTrip,
  rescheduleTrip,
  requestReturn,
  canCancel,
  canReschedule,
  awaitingWillCall,
  CANCELLABLE_STATUSES,
} from "../../api/trips.js";
import { errorMessage } from "../../ui/form-errors.js";
import { openSocket } from "../../api/realtime.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { tripStatusBadge } from "../../ui/badges.js";
import { ratingStars } from "../../ui/rating.js";
import { statusTimeline } from "../../ui/status-timeline.js";
import { loadGoogleMaps } from "../../ui/maps.js";
import { formatCurrency, formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const ACTIVE_STATUSES = ["ASSIGNED", "EN_ROUTE", "ARRIVED", "PICKED_UP"];

const TRACK_NOTE = {
  ASSIGNED: "A driver has been assigned. You'll see them on the map once they head your way.",
  EN_ROUTE: "Your driver is on the way to pick you up.",
  PICKED_UP: "You're on your way to your destination.",
};

const user = await requireRole(["RIDER"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const id = new URLSearchParams(location.search).get("id");
  const content = qs("#content");

  // At most one live-tracking socket at a time (render() rebuilds the page).
  let tracker = null;
  function stopTracker() {
    if (tracker) {
      tracker.close();
      tracker = null;
    }
  }

  const render = (trip) => {
    stopTracker();
    clear(content);
    const detail = el("div", { class: "trip-detail" }, [
      el("p", {}, [tripStatusBadge(trip.status)]),
      el("p", { text: `Pickup: ${formatDateTime(trip.scheduled_pickup_time)}` }),
      el("p", { text: `${trip.pickup_address} → ${trip.dropoff_address}` }),
      el("p", { text: `Mileage: ${trip.mileage ?? "—"}` }),
      el("p", { text: `Service: ${trip.service_name_snapshot || "—"}` }),
      el("p", { text: `Estimated fare: ${formatCurrency(trip.total_cost)}` }),
    ]);
    if (trip.escort_count > 0) {
      detail.append(
        el("p", {
          text: `Travelling with you: ${trip.escort_count} ${trip.escort_count === 1 ? "person" : "people"}`,
        })
      );
    }
    if (trip.trip_type === "ROUND_TRIP") {
      detail.append(
        el("p", {
          class: "page-status-note",
          text: trip.outbound_trip
            ? "This is the return leg of a round trip."
            : "This is the outbound leg of a round trip.",
        })
      );
    }
    if (trip.distance_estimated) {
      detail.append(
        el("p", {
          class: "page-status-note",
          text: "Mileage is an estimate; the final invoice may differ slightly.",
        })
      );
    }
    if (trip.notes) detail.append(el("p", { text: `Notes: ${trip.notes}` }));
    if (trip.cancellation_reason) detail.append(el("p", { text: `Cancellation reason: ${trip.cancellation_reason}` }));
    content.append(detail);

    if (ACTIVE_STATUSES.includes(trip.status)) {
      tracker = mountTracking(trip);
    }

    const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });

    // A will-call return sits idle until the rider says they're ready. Nothing
    // is dispatched before that, so this button is the whole mechanism.
    if (awaitingWillCall(trip)) {
      const callBtn = el("button", {
        class: "btn btn--primary",
        text: "I'm ready to go home",
        onclick: async () => {
          callBtn.disabled = true;
          callBtn.textContent = "Telling dispatch...";
          try {
            const updated = await requestReturn(trip.id);
            render(updated);
            showToast("Dispatch has been told. A driver will be assigned shortly.", {
              type: "success",
            });
          } catch (error) {
            errorEl.textContent = errorMessage(error, "Could not reach dispatch.");
            errorEl.hidden = false;
            callBtn.disabled = false;
            callBtn.textContent = "I'm ready to go home";
          }
        },
      });
      content.append(
        el("div", { class: "willcall-card" }, [
          el("p", { class: "willcall-card__label", text: "Will-call return" }),
          el("p", {
            text: "Nobody is on the way yet. Press this when your appointment is finished and we'll send a driver.",
          }),
          callBtn,
        ])
      );
    } else if (trip.is_will_call && trip.will_call_requested_at) {
      content.append(
        el("p", {
          class: "queue-note",
          text: "You've asked to be collected. Dispatch is assigning a driver.",
        })
      );
    }

    if (canReschedule(trip)) {
      content.append(rescheduleForm(trip, errorEl));
    }

    if (canCancel(trip)) {
      const cancelBtn = el("button", {
        class: "btn btn--danger",
        text: "Cancel trip",
        onclick: async () => {
          cancelBtn.disabled = true;
          try {
            const updated = await cancelTrip(trip.id);
            render(updated);
            showToast("Trip cancelled.", { type: "success" });
          } catch (error) {
            errorEl.textContent = errorMessage(error, "Could not cancel this trip.");
            errorEl.hidden = false;
            cancelBtn.disabled = false;
          }
        },
      });
      content.append(cancelBtn, errorEl);
    } else if (CANCELLABLE_STATUSES.includes(trip.status)) {
      content.append(
        el("p", { class: "page-status-note" }, [
          "It's too close to your pickup to change this trip yourself. Call dispatch on ",
          el("a", { href: "tel:+17015550100", text: "(701) 555-0100" }),
          " and they can move or cancel it for you.",
        ])
      );
    }

    if (trip.status === "COMPLETED") {
      if (trip.rating) {
        const rated = el("div", { class: "trip-detail" }, [
          el("p", { class: "rating-form__label", text: "Your rating" }),
          el("p", {}, [ratingStars(trip.rating)]),
        ]);
        if (trip.review) rated.append(el("p", { class: "rating-review", text: `“${trip.review}”` }));
        content.append(rated);
      } else {
        content.append(renderRatingForm(trip));
      }
    }
  };

  // Live tracking: a Google Map with pickup/drop-off + a moving driver marker,
  // plus a status timeline that advances as the trip progresses. Returns a handle
  // whose close() tears down the WebSocket.
  function mountTracking(trip) {
    const mapEl = el("div", { class: "track__map" });
    const timelineWrap = el("div", { class: "track__timeline" }, [statusTimeline(trip.status)]);
    const note = el("p", { class: "track__note", text: TRACK_NOTE[trip.status] || "" });
    const section = el("section", { class: "track" }, [
      el("h2", { text: "Live tracking" }),
      mapEl,
      timelineWrap,
      note,
    ]);
    content.append(section);

    let currentStatus = trip.status;
    let maps = null;
    let map = null;
    let driverMarker = null;

    loadGoogleMaps()
      .then((mapsApi) => {
        maps = mapsApi;
        const pickup = { lat: Number(trip.pickup_lat), lng: Number(trip.pickup_lng) };
        const dropoff = { lat: Number(trip.dropoff_lat), lng: Number(trip.dropoff_lng) };
        map = new maps.Map(mapEl, { center: pickup, zoom: 12, disableDefaultUI: true, zoomControl: true });
        new maps.Marker({ position: pickup, map, label: "P", title: "Pickup" });
        new maps.Marker({ position: dropoff, map, label: "D", title: "Drop-off" });
        const bounds = new maps.LatLngBounds();
        bounds.extend(pickup);
        bounds.extend(dropoff);
        map.fitBounds(bounds);
      })
      .catch(() => {
        mapEl.replaceWith(
          el("p", { class: "track__map-fallback", text: "Live map unavailable (Google Maps key not configured)." })
        );
      });

    const socket = openSocket(`trips/${trip.id}/track/`, {
      onJson: (msg) => {
        if (msg.event === "driver_location" && map && maps) {
          const pos = { lat: Number(msg.lat), lng: Number(msg.lng) };
          if (!driverMarker) {
            driverMarker = new maps.Marker({
              position: pos,
              map,
              title: "Your driver",
              icon: {
                path: maps.SymbolPath.CIRCLE,
                scale: 8,
                fillColor: "#2563eb",
                fillOpacity: 1,
                strokeColor: "#ffffff",
                strokeWeight: 2,
              },
            });
          } else {
            driverMarker.setPosition(pos);
          }
          map.panTo(pos);
        } else if (msg.event === "status_update" && msg.status !== currentStatus) {
          currentStatus = msg.status;
          if (ACTIVE_STATUSES.includes(msg.status)) {
            timelineWrap.replaceChildren(statusTimeline(msg.status));
            note.textContent = TRACK_NOTE[msg.status] || "";
            showToast(`Trip update: ${msg.status.replace("_", " ").toLowerCase()}.`, { type: "info" });
          } else {
            // Terminal (completed/cancelled/no-show): reload the full detail view.
            getTrip(trip.id).then(render).catch(() => {});
          }
        }
      },
    });

    return { close: () => socket.close() };
  }

  function renderRatingForm(trip) {
    let selected = 0;
    const starBtns = [];
    const starsWrap = el("div", { class: "rating-stars-input" });
    const paint = () => starBtns.forEach((b, idx) => b.classList.toggle("is-on", idx < selected));
    for (let i = 1; i <= 5; i++) {
      const btn = el("button", {
        type: "button",
        class: "rating-star-btn",
        text: "★",
        "aria-label": `${i} star${i > 1 ? "s" : ""}`,
        onclick: () => {
          selected = i;
          paint();
        },
      });
      starBtns.push(btn);
      starsWrap.append(btn);
    }

    const review = el("textarea", { rows: "2", placeholder: "Optional — share a few words about your ride" });
    const err = el("p", { class: "form-error", hidden: "hidden" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Submit rating" });

    const form = el("form", { class: "rating-form" }, [
      el("p", { class: "rating-form__label", text: "Rate your driver" }),
      starsWrap,
      review,
      submit,
      err,
    ]);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (selected < 1) {
        err.textContent = "Please select a star rating.";
        err.hidden = false;
        return;
      }
      submit.disabled = true;
      err.hidden = true;
      try {
        const updated = await rateTrip(trip.id, selected, review.value.trim());
        render(updated);
        showToast("Thanks for rating your ride!", { type: "success" });
      } catch {
        err.textContent = "Could not submit your rating.";
        err.hidden = false;
        submit.disabled = false;
      }
    });
    return form;
  }

  window.addEventListener("beforeunload", stopTracker);

  showLoading(content, "Loading trip...");
  try {
    const trip = await getTrip(id);
    render(trip);
  } catch {
    showError(content, "Could not load this trip.");
  }
}
