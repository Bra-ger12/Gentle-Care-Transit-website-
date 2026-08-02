import {
  requireApprovedDriver,
  getMyDriverProfile,
  updateMyDriverProfile,
  reportLocation,
} from "../../api/drivers.js";
import {
  listTrips,
  getTrip,
  todayParam,
  acceptTrip,
  declineTrip,
  markArrived,
  markEnRoute,
  markPickedUp,
  reportNoShow,
} from "../../api/trips.js";
import { openSocket } from "../../api/realtime.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { tripStatusBadge } from "../../ui/badges.js";
import { mapPanel, vehicleDot, fitTo, tripPoint } from "../../ui/trip-map.js";
import { MOBILITY_LABELS, formatDate } from "../../ui/format.js";
import { ratingSummary } from "../../ui/rating.js";
import {
  relativeWhen,
  labelledRow,
  labelledRows,
  ACTIVE_TRIP_STATUSES,
  LIVE_TRIP_STATUSES,
} from "../../ui/dashboard.js";
import { reasonAction } from "../../ui/reason-action.js";
import { getEarningsSummary } from "../../api/payroll.js";
import { getTodaysInspections } from "../../api/fleet.js";
import { onNotification } from "../../ui/notifications-bell.js";
import { tripCompletionForm } from "../shared/trip-completion-form.js";
import { errorMessage } from "../../ui/form-errors.js";
import { loadServiceAreaSummary } from "../../api/operations.js";
import { showToast } from "../../ui/toast.js";

const DETAIL_BASE = "/driver/trip-detail.html";
const SCHEDULE_BASE = "/driver/schedule.html";
const DVIR_BASE = "/driver/vehicle-check.html";
// Dispatch line, as published on the public site.
const DISPATCH_PHONE = "+17015550100";
const DISPATCH_PHONE_LABEL = "(701) 555-0100";
// Everything a driver can see on a manifest: the live work plus how the day closed out.
const MANIFEST_STATUSES = [...ACTIVE_TRIP_STATUSES, "COMPLETED", "NO_SHOW", "CANCELLED"].join(",");

// At-a-glance state for each manifest row.
const MANIFEST_GLYPH = {
  COMPLETED: "✅",
  EN_ROUTE: "🚦",
  ARRIVED: "📍",
  PICKED_UP: "🚦",
  ASSIGNED: "⏳",
  CONFIRMED: "⏳",
  REQUESTED: "⏳",
  NO_SHOW: "⚠️",
  CANCELLED: "✖️",
};

const VEHICLE_LABELS = {
  SEDAN: "Sedan",
  WHEELCHAIR_VAN: "Wheelchair van",
  STRETCHER_VAN: "Stretcher van",
};

const timeOnly = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);

  const bar = qs("#driver-bar");
  const content = qs("#content");

  const state = {
    profile: null,
    manifest: [],
    /** Detail payload of the trip shown in the Active Trip panel (null when idle). */
    active: null,
    /** Trip the driver picked from the manifest; falls back to the automatic choice. */
    selectedId: null,
    /** Manifest day (YYYY-MM-DD) — the board opens on today but any day is browsable. */
    day: todayParam(),
    /** Earnings totals for `day`, and today's filed vehicle checks. */
    earnings: null,
    inspections: [],
    /** Operator policy: how long to wait before a no-show may be filed, etc. */
    policy: null,
  };

  const isToday = () => state.day === todayParam();

  /** Shift the manifest day by whole days, keeping it a plain YYYY-MM-DD string. */
  function shiftDay(day, delta) {
    const [y, m, d] = day.split("-").map(Number);
    const date = new Date(y, m - 1, d + delta);
    return todayParam(date);
  }

  /** "Today" / "Tomorrow" / a written date, for the manifest heading. */
  function dayLabel(day) {
    if (day === todayParam()) return "Today";
    if (day === shiftDay(todayParam(), 1)) return "Tomorrow";
    if (day === shiftDay(todayParam(), -1)) return "Yesterday";
    const [y, m, d] = day.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }

  // Live panels, kept so a manifest-only refresh can swap one without rebuilding
  // the active trip's map and GPS stream.
  const refs = { grid: null, metrics: null };

  // One GPS stream at a time — every re-render tears the previous one down.
  let streamer = null;
  /** Trip currently streaming this device's location, if any. */
  let streamingTripId = null;
  function stopStreaming() {
    if (streamer) {
      streamer.close();
      streamer = null;
    }
    streamingTripId = null;
  }
  window.addEventListener("beforeunload", stopStreaming);

  /**
   * Report this device's position to dispatch while the driver is on duty.
   *
   * Separate from the per-trip GPS stream above, which only runs during a live
   * trip and only reaches that trip's watchers. This is what puts a driver on
   * the dispatch board between jobs and what lets nearest-driver matching pick
   * them, so it runs whenever they are marked on duty.
   *
   * Failures are swallowed on purpose: a driver in a coverage dead spot still
   * has a working manifest, and a position report is not worth an error banner.
   */
  const LOCATION_INTERVAL_MS = 60_000;
  let locationTimer = null;

  function pushLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        reportLocation(coords.latitude.toFixed(6), coords.longitude.toFixed(6)).catch(() => {});
      },
      () => {},
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 }
    );
  }

  function syncLocationReporting() {
    const onDuty = Boolean(state.profile?.is_available);
    if (onDuty && locationTimer === null) {
      pushLocation();
      locationTimer = setInterval(pushLocation, LOCATION_INTERVAL_MS);
    } else if (!onDuty && locationTimer !== null) {
      clearInterval(locationTimer);
      locationTimer = null;
    }
  }

  window.addEventListener("beforeunload", () => {
    if (locationTimer !== null) clearInterval(locationTimer);
  });

  /** The trip the ops panel should show: the live one, else the soonest actionable one. */
  function pickActive(manifest, upcoming) {
    if (state.selectedId) {
      const chosen = manifest.find((t) => t.id === state.selectedId);
      if (chosen) return chosen;
    }
    const live = manifest.find((t) => LIVE_TRIP_STATUSES.includes(t.status));
    if (live) return live;
    const actionable = manifest.find((t) => ACTIVE_TRIP_STATUSES.includes(t.status));
    if (actionable) return actionable;
    // Falling back to the next assignment only makes sense on today's board; while
    // browsing another day, show that day's first trip or nothing.
    return isToday() ? upcoming || null : manifest[0] || null;
  }

  async function load() {
    stopStreaming();
    showLoading(content, `Loading the manifest for ${dayLabel(state.day).toLowerCase()}...`);
    try {
      const [profile, manifest, active, earnings, inspections, policy] = await Promise.all([
        getMyDriverProfile().catch(() => null),
        listTrips(1, MANIFEST_STATUSES, { date: state.day }),
        listTrips(1, ACTIVE_TRIP_STATUSES.join(",")),
        // Pay for the day being viewed; a driver with no rate on file gets nulls
        // rather than a broken board.
        getEarningsSummary({ dateFrom: state.day, dateTo: state.day }).catch(() => null),
        isToday() ? getTodaysInspections().catch(() => []) : Promise.resolve([]),
        loadServiceAreaSummary(),
      ]);
      state.profile = profile;
      state.policy = policy;
      syncLocationReporting();
      state.manifest = manifest.results;
      state.earnings = earnings;
      state.inspections = inspections;

      const chosen = pickActive(manifest.results, active.results[0]);
      state.active = chosen ? await getTrip(chosen.id).catch(() => null) : null;

      renderBar();
      renderOps();
    } catch {
      showError(content, "Could not load your manifest.");
    }
  }

  /** Reload after a status change, keeping the driver on the same trip. */
  async function reload(tripId) {
    if (tripId) state.selectedId = tripId;
    await load();
  }

  /** Jump the manifest to another day; the panel follows that day's first trip. */
  function goToDay(day) {
    state.day = day;
    state.selectedId = null;
    load();
  }

  /**
   * Re-read today's manifest and repaint just that column plus the metrics bar.
   * Used while a trip is streaming location, where a full reload would restart the
   * GPS watch and rebuild the map for a change the driver didn't make.
   */
  async function refreshManifest() {
    // A failed load leaves an error page behind, not the grid — rebuild instead.
    if (!refs.grid || !refs.grid.isConnected) return load();
    try {
      const [manifest, earnings] = await Promise.all([
        listTrips(1, MANIFEST_STATUSES, { date: state.day }),
        getEarningsSummary({ dateFrom: state.day, dateTo: state.day }).catch(() => state.earnings),
      ]);
      state.manifest = manifest.results;
      state.earnings = earnings;
      refs.grid.replaceChild(manifestPanel(), refs.grid.firstElementChild);
      const metrics = metricsBar();
      refs.metrics.replaceWith(metrics);
      refs.metrics = metrics;
    } catch {
      // leave the current board up — the next event or action will refresh it
    }
  }

  // Dispatch assigns and cancels trips while the driver is on the road, so the board
  // follows the bell's socket instead of waiting for a manual refresh. Only
  // trip-related notifications matter here.
  let notifyTimer = null;
  onNotification((notification) => {
    if (!notification.related_trip) return;
    clearTimeout(notifyTimer);
    notifyTimer = setTimeout(() => {
      // A change to the trip being driven (e.g. dispatch cancels it) still needs the
      // full rebuild; anything else leaves the active panel and its stream alone.
      if (streamingTripId && notification.related_trip !== streamingTripId) refreshManifest();
      else load();
    }, 800);
  });

  // --- Top bar: who's driving, what they're driving, duty status, dispatch line ---

  function renderBar() {
    const profile = state.profile;
    // The mockup's "Van #4" — the system identifies a vehicle by type and plate,
    // which is what an admin actually assigns, so that's what's shown.
    const vehicle = profile
      ? [VEHICLE_LABELS[profile.vehicle_type] || profile.vehicle_type, profile.vehicle_plate]
          .filter(Boolean)
          .join(" · ")
      : "";

    const identity = el("div", { class: "ops-bar__identity" }, [
      el("span", { class: "ops-bar__label", text: "Driver" }),
      el("span", { class: "ops-bar__name", text: `${user.first_name} ${user.last_name}` }),
      vehicle ? el("span", { class: "chip ops-bar__vehicle", text: vehicle }) : null,
      profile && profile.ratings_count
        ? ratingSummary(profile.average_rating, profile.ratings_count)
        : null,
    ]);

    const actions = el("div", { class: "ops-bar__actions" }, [
      profile ? dutyToggle(profile) : null,
      el("a", {
        class: "btn btn--danger ops-bar__sos",
        href: `tel:${DISPATCH_PHONE}`,
        title: `Call dispatch ${DISPATCH_PHONE_LABEL}`,
        "aria-label": `Call dispatch ${DISPATCH_PHONE_LABEL}`,
      }, ["🆘", el("span", { class: "ops-bar__sos-text", text: "Dispatch" })]),
    ]);

    bar.className = "ops-bar";
    bar.replaceChildren(identity, actions);
  }

  /** On/Off duty control — the driver's `is_available` flag, which dispatch assigns against. */
  function dutyToggle(profile) {
    let available = Boolean(profile.is_available);
    const wrap = el("div", { class: "duty" });

    // One pill that both shows duty state and toggles it, as drawn.
    const draw = () => {
      const button = el(
        "button",
        {
          class: `duty-pill${available ? " duty-pill--on" : ""}`,
          type: "button",
          title: available ? "Tap to go off duty" : "Tap to go on duty",
          onclick: async () => {
            button.disabled = true;
            try {
              const updated = await updateMyDriverProfile({ is_available: !available });
              available = Boolean(updated.is_available);
              state.profile = { ...state.profile, is_available: available };
              // Going on duty starts position reporting; going off stops it, so
              // the board never shows a driver who has finished for the day.
              syncLocationReporting();
              draw();
              showToast(available ? "You're on duty." : "You're off duty.", { type: "success" });
            } catch {
              button.disabled = false;
              showToast("Could not update your duty status.", { type: "error" });
            }
          },
        },
        [
          el("span", { class: `avail-dot ${available ? "avail-dot--on" : "avail-dot--off"}` }),
          el("span", { text: available ? "ON DUTY" : "OFF DUTY" }),
        ]
      );
      wrap.replaceChildren(button);
    };

    draw();
    return wrap;
  }

  /** Day stepper: any date is browsable, "Today" snaps back to the live board. */
  function dayNav() {
    const picker = el("input", { type: "date", class: "day-nav__date", value: state.day });
    picker.addEventListener("change", () => {
      if (picker.value) goToDay(picker.value);
    });

    const step = (label, delta, title) =>
      el("button", {
        class: "btn day-nav__step",
        type: "button",
        text: label,
        title,
        "aria-label": title,
        onclick: () => goToDay(shiftDay(state.day, delta)),
      });

    return el("div", { class: "day-nav" }, [
      step("‹", -1, "Previous day"),
      picker,
      step("›", 1, "Next day"),
      isToday()
        ? null
        : el("button", { class: "btn day-nav__today", type: "button", text: "Today", onclick: () => goToDay(todayParam()) }),
      el("a", { class: "day-nav__all", href: SCHEDULE_BASE, text: "Full schedule" }),
    ]);
  }

  // --- Two-column operations layout + bottom metrics ---

  function renderOps() {
    clear(content);
    refs.grid = el("div", { class: "ops-grid" }, [manifestPanel(), activePanel()]);
    refs.metrics = metricsBar();
    content.append(refs.grid, refs.metrics);
  }

  function manifestPanel() {
    const panel = el("section", { class: "ops-panel" }, [
      el("div", { class: "ops-panel__head" }, [
        el("h2", { class: "ops-panel__title", text: `${dayLabel(state.day)}'s manifest` }),
        el("span", { class: "ops-panel__meta", text: formatDate(`${state.day}T00:00:00`) }),
      ]),
      dayNav(),
    ]);

    if (state.manifest.length === 0) {
      panel.append(
        el("p", { class: "empty-state", text: `Nothing scheduled for ${dayLabel(state.day).toLowerCase()}.` }),
        el("p", {
          class: "ops-panel__note",
          text: isToday()
            ? "New assignments from dispatch appear here as soon as they're made."
            : "Use the arrows to check another day, or open your full schedule.",
        }),
        el("a", { class: "ops-workflow__link", href: SCHEDULE_BASE, text: "Your full schedule" })
      );
      return panel;
    }

    const activeId = state.active ? state.active.id : null;
    panel.append(
      el(
        "ul",
        { class: "manifest" },
        state.manifest.map((trip) => {
          const isCurrent = trip.id === activeId;
          return el("li", {}, [
            el(
              "button",
              {
                class: `manifest__row${isCurrent ? " is-current" : ""}`,
                type: "button",
                "aria-current": isCurrent ? "true" : null,
                onclick: () => reload(trip.id),
              },
              [
                el("span", { class: "manifest__glyph", text: MANIFEST_GLYPH[trip.status] || "•" }),
                el("span", { class: "manifest__time mono", text: timeOnly(trip.scheduled_pickup_time) }),
                el("span", { class: "manifest__body" }, [
                  el("span", { class: "manifest__route", text: trip.dropoff_address }),
                  el("span", { class: "manifest__pickup", text: `from ${trip.pickup_address}` }),
                ]),
                el("span", { class: "manifest__status" }, [
                  tripStatusBadge(trip.status),
                  trip.mobility_need
                    ? el("span", {
                        class: "chip",
                        text: MOBILITY_LABELS[trip.mobility_need] || trip.mobility_need,
                      })
                    : null,
                ]),
              ]
            ),
          ]);
        })
      )
    );
    return panel;
  }

  function activePanel() {
    const trip = state.active;
    const panel = el("section", { class: "ops-panel ops-panel--active" });

    if (!trip) {
      panel.append(
        el("div", { class: "ops-panel__head" }, [el("h2", { class: "ops-panel__title", text: "Active trip" })]),
        el("p", { class: "empty-state", text: "No trip in progress." }),
        el("p", {
          class: "ops-panel__note",
          text: "When dispatch assigns your next ride it opens here with the passenger details and your route.",
        })
      );
      return panel;
    }

    const isToday = state.manifest.some((t) => t.id === trip.id);
    const heading = isToday ? "Active trip" : "Next assignment";

    panel.append(
      el("div", { class: "ops-panel__head" }, [
        el("h2", { class: "ops-panel__title" }, [
          `${heading}: `,
          el("span", { class: "ops-panel__subject", text: trip.rider_name || "Passenger" }),
        ]),
        el("div", { class: "ops-panel__badges" }, [
          tripStatusBadge(trip.status),
          el("span", { class: "ops-panel__meta", text: relativeWhen(trip.scheduled_pickup_time) }),
        ]),
      ]),
      detailRows(trip)
    );

    if (trip.notes) {
      panel.append(
        el("p", { class: "ops-notes" }, [
          el("span", { class: "ops-notes__icon", text: "⚠️" }),
          el("span", {}, [el("strong", { text: "Note: " }), trip.notes]),
        ])
      );
    }

    panel.append(mountMap(trip), navigationLink(trip), workflowBlock(trip));
    return panel;
  }

  function detailRows(trip) {
    const needs = trip.rider_mobility_needs || [];
    return labelledRows([
      labelledRow(
        "👤",
        "Passenger",
        el("span", { text: trip.rider_name || "—" }),
        trip.rider_phone
          ? el("a", { class: "btn ops-row__action", href: `tel:${trip.rider_phone}`, text: "Call" })
          : el("span", { class: "ops-row__muted", text: "no phone on file" })
      ),
      labelledRow(
        "♿",
        "Needs",
        el("span", {
          text: needs.length > 0 ? needs.map((n) => MOBILITY_LABELS[n] || n).join(" / ") : "None recorded",
        })
      ),
      labelledRow("📍", "Pickup", el("span", { text: trip.pickup_address })),
      labelledRow("🏁", "Dropoff", el("span", { text: trip.dropoff_address })),
      labelledRow(
        "⏱️",
        "Scheduled pickup",
        el("span", { class: "mono", text: timeOnly(trip.scheduled_pickup_time) })
      ),
    ]);
  }

  /** Hand the route to the phone's own navigation app. */
  function navigationLink(trip) {
    const from = tripPoint(trip, "pickup");
    const to = tripPoint(trip, "dropoff");
    if (!from || !to) return el("p", { class: "ops-panel__note", text: "Route not geocoded — no navigation link." });

    // Navigate to the pickup while heading there, to the destination once carrying.
    const target = trip.status === "PICKED_UP" ? to : from;
    const url = new URL("https://www.google.com/maps/dir/");
    url.searchParams.set("api", "1");
    url.searchParams.set("destination", `${target.lat},${target.lng}`);
    url.searchParams.set("travelmode", "driving");

    return el("a", {
      class: "btn btn--primary ops-nav",
      href: url.toString(),
      target: "_blank",
      rel: "noopener",
      text: `🧭 Open navigation to ${trip.status === "PICKED_UP" ? "drop-off" : "pickup"}`,
    });
  }

  /**
   * Route map for the active trip. While en route / carrying the passenger this
   * device also streams its GPS position over the trip socket (the rider's page
   * follows it) and drops the same position on the driver's own map.
   */
  function mountMap(trip) {
    const { element, whenReady } = mapPanel({ className: "ops-map" });
    const wrap = el("div", { class: "ops-map-wrap" }, [element]);
    const pickup = tripPoint(trip, "pickup");
    const dropoff = tripPoint(trip, "dropoff");

    const ready = whenReady.then((ctx) => {
      if (!ctx) return null;
      const { maps, map } = ctx;
      if (pickup) new maps.Marker({ position: pickup, map, label: "P", title: "Pickup" });
      if (dropoff) new maps.Marker({ position: dropoff, map, label: "D", title: "Drop-off" });
      fitTo(maps, map, [pickup, dropoff]);
      return ctx;
    });

    if (LIVE_TRIP_STATUSES.includes(trip.status)) {
      wrap.append(startStreaming(trip, ready));
    }
    return wrap;
  }

  function startStreaming(trip, ready) {
    const text = el("span", { class: "geo-pill__text", text: "Sharing your location with the passenger…" });
    const pill = el("div", { class: "geo-pill" }, [el("span", { class: "geo-pill__dot" }), text]);

    const socket = openSocket(`trips/${trip.id}/track/`);
    let watchId = null;
    let marker = null;

    const showSelf = async (pos) => {
      const ctx = await ready;
      if (!ctx) return;
      const { maps, map } = ctx;
      const position = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      if (marker) marker.setPosition(position);
      else marker = new maps.Marker({ position, map, title: "You", icon: vehicleDot(maps) });
    };

    if ("geolocation" in navigator) {
      watchId = navigator.geolocation.watchPosition(
        (pos) => {
          socket.send({ type: "location", lat: pos.coords.latitude, lng: pos.coords.longitude });
          showSelf(pos);
        },
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

    streamingTripId = trip.id;
    streamer = {
      close: () => {
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        socket.close();
      },
    };
    return pill;
  }

  /**
   * The three-step workflow from the mockup. Each step is a numbered button:
   * done steps read as done, the one the trip is waiting on is the only one
   * enabled, later steps stay greyed out. The labels track the real state
   * machine — step 1 puts the trip EN_ROUTE (heading to the pickup), which is
   * what the system records; it doesn't claim an arrival nothing tracks.
   */
  // Set by workflowBlock so the wait clock, rendered alongside it, can report a
  // no-show through the same error banner and reload path.
  let runNoShow = null;

  const WORKFLOW_STEPS = [
    {
      label: "En route to pickup",
      done: ["EN_ROUTE", "ARRIVED", "PICKED_UP", "COMPLETED"],
      at: "ASSIGNED",
      run: (trip) => markEnRoute(trip.id),
      toast: "You're en route.",
    },
    {
      label: "Arrived at pickup",
      done: ["ARRIVED", "PICKED_UP", "COMPLETED"],
      at: "EN_ROUTE",
      run: (trip) => markArrived(trip.id),
      toast: "Arrival recorded — the wait clock has started.",
    },
    {
      label: "Passenger boarded",
      done: ["PICKED_UP", "COMPLETED"],
      at: "ARRIVED",
      run: (trip) => markPickedUp(trip.id),
      toast: "Passenger picked up.",
    },
    {
      label: "Complete drop-off",
      done: ["COMPLETED"],
      at: "PICKED_UP",
      // Completion needs odometer readings, the rider's name and their
      // signature, so this step reveals that form rather than firing a bare
      // transition.
      form: true,
    },
  ];

  /**
   * The wait at the door, counting up, with the no-show control unlocking when
   * the required minutes are up.
   *
   * The server enforces the wait regardless; showing the clock is what stops a
   * driver hammering a button that will keep refusing them, and what makes the
   * rule visible rather than mysterious.
   */
  function waitClock(trip) {
    const required = state.policy?.no_show_wait_minutes ?? 10;
    const elapsed = () => (Date.now() - new Date(trip.arrived_at).getTime()) / 60000;

    const readout = el("p", { class: "wait-clock__readout", "aria-live": "polite" });
    const slot = el("div", { class: "wait-clock__action" });
    const block = el("div", { class: "wait-clock" }, [
      el("p", { class: "wait-clock__label", text: "Waiting at pickup" }),
      readout,
      slot,
    ]);

    const noShowControl = reasonAction({
      trigger: "Report no-show",
      triggerClass: "btn btn--danger",
      placeholder: "What happened at the pickup? (this goes on the claim)",
      confirm: "Confirm no-show",
      onSubmit: (reason, button) =>
        runNoShow(button, () => reportNoShow(trip.id, reason)),
    });

    let unlocked = false;
    function tick() {
      if (!block.isConnected) {
        clearInterval(timer);
        return;
      }
      const minutes = Math.max(0, Math.floor(elapsed()));
      const remaining = Math.max(0, Math.ceil(required - elapsed()));

      readout.textContent = `${minutes} min`;
      if (remaining > 0) {
        slot.replaceChildren(
          el("p", {
            class: "wait-clock__hint",
            text: `A no-show can be filed after ${required} minutes — ${remaining} to go.`,
          })
        );
      } else if (!unlocked) {
        unlocked = true;
        block.classList.add("wait-clock--unlocked");
        slot.replaceChildren(noShowControl);
      }
    }

    const timer = setInterval(tick, 1000);
    tick();
    return block;
  }

  function workflowBlock(trip) {
    const block = el("div", { class: "ops-workflow" }, [
      el("p", { class: "ops-workflow__label", text: "Trip workflow" }),
    ]);
    const errorEl = el("p", { class: "form-error", hidden: "hidden" });

    runNoShow = async (button, fn) => {
      button.disabled = true;
      errorEl.hidden = true;
      try {
        await fn();
        showToast("No-show reported.", { type: "success" });
        reload(trip.id);
      } catch (error) {
        errorEl.textContent = errorMessage(error, "Could not file this no-show.");
        errorEl.hidden = false;
        button.disabled = false;
      }
    };

    const runStep = async (button, fn, toast) => {
      button.disabled = true;
      errorEl.hidden = true;
      try {
        await fn();
        showToast(toast, { type: "success" });
        reload(trip.id);
      } catch (error) {
        errorEl.textContent = errorMessage(error, "Could not update this trip. Try again, or call dispatch.");
        errorEl.hidden = false;
        button.disabled = false;
      }
    };

    // A trip the driver hasn't taken yet gates the whole workflow.
    const awaitingAcceptance = trip.status === "ASSIGNED" && !trip.accepted_at;
    if (awaitingAcceptance) {
      const accept = el("button", { class: "btn btn--primary", text: "Accept this assignment" });
      accept.addEventListener("click", () => runStep(accept, () => acceptTrip(trip.id), "Trip accepted."));
      block.append(
        el("div", { class: "ops-workflow__accept" }, [
          accept,
          // Dispatch has to reassign a declined trip, so they get told why.
          reasonAction({
            trigger: "Decline",
            placeholder: "Why you can't take this trip (dispatch sees this)",
            confirm: "Confirm decline",
            onSubmit: (reason, button) => runStep(button, () => declineTrip(trip.id, reason), "Trip declined."),
          }),
        ])
      );
    }

    const completionForm = el("div", { class: "inline-form collapsible" }, [
      tripCompletionForm(trip.id, () => reload(trip.id)),
    ]);

    const steps = WORKFLOW_STEPS.map((step, index) => {
      const isDone = step.done.includes(trip.status);
      const isCurrent = !awaitingAcceptance && trip.status === step.at;
      const button = el(
        "button",
        {
          type: "button",
          class: `ops-step${isDone ? " ops-step--done" : ""}${isCurrent ? " ops-step--current" : ""}`,
          disabled: isCurrent ? undefined : "disabled",
        },
        [
          el("span", { class: "ops-step__num", text: isDone ? "✓" : String(index + 1) }),
          el("span", { class: "ops-step__label", text: step.label }),
        ]
      );
      if (isCurrent) {
        button.addEventListener("click", () => {
          if (step.form) completionForm.classList.add("is-open");
          else runStep(button, () => step.run(trip), step.toast);
        });
      }
      return button;
    });

    block.append(el("div", { class: "ops-steps" }, steps), completionForm);

    // A passenger who never shows closes the trip from the arrived step -- the
    // driver has to be at the door, and the wait clock that justifies the claim
    // runs from the arrival they just recorded.
    if (trip.status === "ARRIVED") {
      block.append(el("div", { class: "ops-workflow__aside" }, [waitClock(trip)]));
    }
    if (!ACTIVE_TRIP_STATUSES.includes(trip.status)) {
      block.append(el("p", { class: "ops-panel__note", text: "This trip is closed — nothing left to do." }));
    }

    block.append(
      errorEl,
      el("a", { class: "ops-workflow__link", href: `${DETAIL_BASE}?id=${trip.id}`, text: "Full trip record" })
    );
    return block;
  }

  // --- Bottom metrics bar ---

  function metricsBar() {
    const scheduled = state.manifest.filter((t) => t.status !== "CANCELLED");
    const completed = scheduled.filter((t) => t.status === "COMPLETED");
    const noShows = scheduled.filter((t) => t.status === "NO_SHOW").length;
    const miles = completed.reduce((sum, t) => sum + Number(t.mileage || 0), 0);
    const profile = state.profile;

    const metric = (label, value, hint) =>
      el("div", { class: "ops-metric" }, [
        el("span", { class: "ops-metric__label", text: label }),
        el("span", { class: "ops-metric__value", text: value }),
        hint ? el("span", { class: "ops-metric__hint", text: hint }) : null,
      ]);

    // DVIR: one pre-trip and one post-trip check per day; the button reports
    // what's still outstanding so a driver can see it without opening the form.
    const filedTypes = new Set(state.inspections.map((i) => i.inspection_type));
    const flagged = state.inspections.some((i) => i.needs_attention);
    const dvirState = !isToday()
      ? "Vehicle check"
      : flagged
        ? "⚠️ Defects reported"
        : filedTypes.size === 0
          ? "Vehicle check due"
          : filedTypes.has("PRE_TRIP") && filedTypes.has("POST_TRIP")
            ? "✅ Checks complete"
            : filedTypes.has("PRE_TRIP")
              ? "Post-trip check due"
              : "Pre-trip check due";

    const vehicleCheck = el("a", {
      class: `btn ${flagged ? "btn--danger" : filedTypes.size === 0 && isToday() ? "btn--primary" : ""}`.trim(),
      href: DVIR_BASE,
      text: `📊 ${dvirState}`,
    });

    const earnings = state.earnings;
    const earned = earnings ? `$${Number(earnings.total_earned).toFixed(2)}` : "—";
    const earnedHint = !earnings
      ? "no pay rate on file"
      : Number(earnings.unpaid_amount) > 0
        ? `$${Number(earnings.unpaid_amount).toFixed(2)} unpaid`
        : "paid out";

    return el("section", { class: "ops-metrics" }, [
      el("div", { class: "ops-metric ops-metric--action" }, [vehicleCheck]),
      metric(
        "Trips",
        `${completed.length}/${scheduled.length}`,
        noShows > 0 ? `${noShows} no-show` : "completed of scheduled"
      ),
      metric("Miles", miles > 0 ? miles.toFixed(1) : "0", "booked mileage"),
      metric("Earnings", earned, earnedHint),
      metric(
        "Vehicle",
        profile
          ? [VEHICLE_LABELS[profile.vehicle_type] || profile.vehicle_type, profile.vehicle_plate]
              .filter(Boolean)
              .join(" · ") || "—"
          : "—",
        profile && profile.vehicle_capacity ? `${profile.vehicle_capacity} seats` : null
      ),
    ]);
  }

  load();
}
