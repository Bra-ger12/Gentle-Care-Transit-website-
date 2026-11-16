import { requireRole } from "../../api/auth.js";
import {
  listTrips,
  assignTrip,
  driverSuggestions,
  autoAssignTrip,
  confirmTrip,
  cancelTrip,
  reassignTrip,
  todayParam,
} from "../../api/trips.js";
import { listAllDrivers } from "../../api/drivers.js";
import { openSocket } from "../../api/realtime.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { renderHero, greetingTitle } from "../../ui/hero.js";
import { showEmpty } from "../../ui/status.js";
import { tripStatusBadge, licenseBadge } from "../../ui/badges.js";
import { ratingSummary } from "../../ui/rating.js";
import { formatCurrency, formatDateTime, MOBILITY_LABELS } from "../../ui/format.js";
import { statCards, LIVE_TRIP_STATUSES } from "../../ui/dashboard.js";
import { listOnDutyDrivers } from "../../api/drivers.js";
import { mapPanel, vehicleDot, fitTo, tripPoint } from "../../ui/trip-map.js";
import { showToast } from "../../ui/toast.js";
import { errorMessage } from "../../ui/form-errors.js";

// Every state where a driver is committed to a trip. ARRIVED belongs here:
// a driver standing at a rider's door is very much in flight, and leaving it
// out drops them off the board mid-trip.
const IN_FLIGHT_STATUSES = "ASSIGNED,EN_ROUTE,ARRIVED,PICKED_UP";
// Cap on simultaneous per-trip tracking sockets held open by one dispatch board.
const MAX_TRACKED = 12;

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Dispatch",
    title: greetingTitle(user),
    lead: "Assign confirmed trips, track rides in progress, and keep today's schedule on time.",
  });

  const content = qs("#content");
  const selectedDrivers = {};

  // The shell is built once — refreshes repaint the sections but never recreate the
  // map, so the dispatcher's pan/zoom and the live vehicle dots survive updates.
  const overview = el("div", { class: "dash-overview" });
  const requestSection = el("section", { class: "dash-section" });
  const crewSection = el("section", { class: "dash-section" });
  const queueSection = el("section", { class: "dash-section" });
  const inFlightSection = el("section", { class: "dash-section" });
  const fleetNote = el("p", { class: "section-lead" });
  const fleet = mapPanel({ className: "fleet-map" });
  const fleetSection = el("section", { class: "dash-section" }, [
    el("h2", { text: "Live fleet map" }),
    fleetNote,
    fleet.element,
  ]);
  // A failed refresh must not tear the board down — the poll and the socket both
  // keep calling load(), so the banner just reports the last attempt.
  const boardError = el("p", {
    class: "page-status",
    hidden: "hidden",
    text: "Could not refresh the dispatch board — retrying.",
  });
  const bootStatus = el("p", { class: "page-status", text: "Loading the dispatch board..." });
  content.replaceChildren(
    boardError,
    overview,
    crewSection,
    requestSection,
    queueSection,
    inFlightSection,
    fleetSection,
    bootStatus
  );

  async function load() {
    try {
      const [today, needsAssignment, inFlight, requested, drivers, onDuty] = await Promise.all([
        listTrips(1, undefined, { date: todayParam() }),
        listTrips(1, "CONFIRMED"),
        listTrips(1, IN_FLIGHT_STATUSES),
        listTrips(1, "REQUESTED"),
        listAllDrivers(true),
        listOnDutyDrivers().catch(() => []),
      ]);
      bootStatus.remove();
      boardError.hidden = true;

      renderOverview({ today, needsAssignment, inFlight, requested, drivers });
      renderCrew(drivers.results, inFlight.results, onDuty);
      renderRequests(requested.results);
      renderQueue(needsAssignment.results, drivers.results);
      renderInFlight(inFlight.results, drivers.results);
      syncFleet(inFlight.results, onDuty);
    } catch {
      bootStatus.remove();
      boardError.hidden = false;
    }
  }

  // --- Today's overview ---

  function renderOverview({ today, needsAssignment, inFlight, requested, drivers }) {
    // Hints derived from a result page are only quoted when that page is the whole
    // set — otherwise the tile shows the server's count alone rather than a
    // number that silently stops at 20.
    const whole = (payload) => payload.count === payload.results.length;
    const completedToday = today.results.filter((t) => t.status === "COMPLETED").length;
    const enRoute = inFlight.results.filter((t) => LIVE_TRIP_STATUSES.includes(t.status)).length;
    const onDuty = drivers.results.filter((d) => d.is_available).length;

    overview.replaceChildren(
      el("h2", { text: "Today's overview" }),
      statCards([
        {
          label: "Trips today",
          value: today.count,
          hint: whole(today) ? `${completedToday} completed` : null,
        },
        {
          label: "In flight",
          value: inFlight.count,
          hint: whole(inFlight) ? `${enRoute} carrying or en route` : null,
          accent: true,
        },
        {
          label: "Awaiting assignment",
          value: needsAssignment.count,
          hint: `${requested.count} awaiting confirmation`,
        },
        {
          label: "Drivers on duty",
          value: `${onDuty}/${drivers.count}`,
          hint: "of the approved roster",
        },
      ])
    );
  }

  // --- Who's on duty right now ---

  /**
   * The roster dispatch assigns from: who's online, what they drive, and how
   * loaded they already are. On-duty drivers come first — an off-duty driver can
   * still be assigned (the API allows it), but dispatch should see the state.
   */
  /**
   * Where a driver was last seen, in words.
   *
   * A stale fix is labelled as stale rather than shown as a position: a
   * dispatcher steering by a 40-minute-old location is worse off than one who
   * knows they have nothing to steer by.
   */
  function positionLine(status) {
    if (!status) return null;
    if (status.lat === null) {
      return el("p", {
        class: "crew__where crew__where--unknown",
        text: "Location not shared - their app hasn't reported in.",
      });
    }
    if (status.position_is_stale) {
      return el("p", {
        class: "crew__where crew__where--stale",
        text: `Last seen ${status.position_age_minutes} min ago - too old to route by.`,
      });
    }
    const age =
      status.position_age_minutes <= 1 ? "just now" : `${status.position_age_minutes} min ago`;
    const doing = status.current_trip_dropoff
      ? ` - heading to ${status.current_trip_dropoff}`
      : " - between jobs";
    return el("p", { class: "crew__where" }, [
      el("span", { class: "crew__pin", text: "\u{1F4CD}", "aria-hidden": "true" }),
      el("span", { text: `Located ${age}${doing}` }),
    ]);
  }

  function renderCrew(drivers, inFlight, onDuty = []) {
    clear(crewSection);
    crewSection.append(el("h2", { text: "Drivers on duty" }));

    if (drivers.length === 0) {
      showEmpty(crewSection, "No approved drivers yet — approve one on the Drivers page before assigning work.");
      return;
    }

    // Current workload, counted from the trips already in flight.
    const load = new Map();
    for (const trip of inFlight) {
      if (!trip.assigned_driver) continue;
      const entry = load.get(trip.assigned_driver) || { total: 0, live: 0 };
      entry.total += 1;
      if (LIVE_TRIP_STATUSES.includes(trip.status)) entry.live += 1;
      load.set(trip.assigned_driver, entry);
    }

    const ordered = [...drivers].sort((a, b) => {
      if (a.is_available !== b.is_available) return a.is_available ? -1 : 1;
      const aLoad = (load.get(a.id) || { total: 0 }).total;
      const bLoad = (load.get(b.id) || { total: 0 }).total;
      if (aLoad !== bLoad) return aLoad - bLoad; // freest first
      return `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`);
    });

    // Position and current job come from the on-duty feed, keyed by driver id.
    const byId = new Map(onDuty.map((row) => [row.id, row]));
    const online = ordered.filter((d) => d.is_available).length;
    const located = onDuty.filter((row) => row.lat !== null && !row.position_is_stale).length;
    crewSection.append(
      el("p", {
        class: "section-lead",
        text:
          `${online} of ${drivers.length} approved driver${drivers.length === 1 ? "" : "s"} on duty` +
          `, ${located} sharing a current location. Free drivers are listed first.`,
      }),
      el(
        "div",
        { class: "crew" },
        ordered.map((driver) => {
          const busy = load.get(driver.id) || { total: 0, live: 0 };
          const vehicle = [driver.vehicle_type, driver.vehicle_plate].filter(Boolean).join(" · ");
          return el("article", { class: `crew__card${driver.is_available ? "" : " crew__card--off"}` }, [
            el("div", { class: "crew__head" }, [
              el("span", { class: "crew__name", text: `${driver.first_name} ${driver.last_name}`.trim() || driver.email }),
              el("span", { class: "crew__duty" }, [
                el("span", { class: `avail-dot ${driver.is_available ? "avail-dot--on" : "avail-dot--off"}` }),
                el("span", { text: driver.is_available ? "On duty" : "Off duty" }),
              ]),
            ]),
            el("p", { class: "crew__vehicle", text: vehicle || "No vehicle on file" }),
            positionLine(byId.get(driver.id)),
            el("p", { class: "crew__load" }, [
              busy.total === 0
                ? el("span", { class: "crew__free", text: "Free — no trips in flight" })
                : el("span", {
                    text: `${busy.total} trip${busy.total === 1 ? "" : "s"} assigned${busy.live > 0 ? ` · ${busy.live} on the road` : ""}`,
                  }),
            ]),
            driver.ratings_count
              ? el("p", { class: "crew__rating" }, [ratingSummary(driver.average_rating, driver.ratings_count)])
              : null,
            licenseBadge(driver),
          ]);
        })
      )
    );
  }

  // --- New requests (awaiting confirmation) ---

  /**
   * A rider's booking lands in REQUESTED and only reaches the assignment queue
   * once dispatch confirms it. Declining closes the request with a reason the
   * rider is notified about.
   */
  function renderRequests(trips) {
    clear(requestSection);
    requestSection.append(el("h2", { text: "New requests — awaiting confirmation" }));
    if (trips.length === 0) {
      showEmpty(requestSection, "No new booking requests.");
      return;
    }

    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const rows = trips.map((trip) => {
      const confirmBtn = el("button", {
        class: "btn btn--primary",
        text: "Confirm",
        onclick: async () => {
          confirmBtn.disabled = true;
          errorEl.hidden = true;
          try {
            await confirmTrip(trip.id);
            showToast("Trip confirmed — it's now ready to assign.", { type: "success" });
            load();
          } catch {
            errorEl.textContent = "Could not confirm that request.";
            errorEl.hidden = false;
            confirmBtn.disabled = false;
          }
        },
      });

      // Declining needs a reason: it's what the rider sees in their notification.
      const declineBtn = el("button", { class: "btn btn--danger", text: "Decline" });
      const declineForm = el("div", { class: "inline-form collapsible" });
      const reasonInput = el("input", { type: "text", placeholder: "Reason the rider will see", required: "required" });
      const declineConfirm = el("button", { class: "btn btn--danger", text: "Confirm decline", disabled: "disabled" });
      reasonInput.addEventListener("input", () => {
        declineConfirm.disabled = reasonInput.value.trim().length === 0;
      });
      declineConfirm.addEventListener("click", async () => {
        declineConfirm.disabled = true;
        errorEl.hidden = true;
        try {
          await cancelTrip(trip.id, reasonInput.value.trim());
          showToast("Request declined.", { type: "info" });
          load();
        } catch {
          errorEl.textContent = "Could not decline that request.";
          errorEl.hidden = false;
          declineConfirm.disabled = false;
        }
      });
      declineBtn.addEventListener("click", () => declineForm.classList.toggle("is-open"));
      declineForm.append(reasonInput, el("div", { class: "inline-form__actions" }, [declineConfirm]));

      return el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: formatDateTime(trip.scheduled_pickup_time) }),
        el("td", {}, [
          el("div", { text: `${trip.pickup_address} → ${trip.dropoff_address}` }),
          trip.mobility_need
            ? el("span", { class: "chip", text: MOBILITY_LABELS[trip.mobility_need] || trip.mobility_need })
            : null,
          trip.total_cost ? el("div", { class: "queue-note", text: `Fare: ${formatCurrency(trip.total_cost)}` }) : null,
          declineForm,
        ]),
        el("td", { class: "dispatch-table__actions" }, [confirmBtn, declineBtn]),
      ]);
    });

    requestSection.append(dataTable(["Pickup", "Route", "Actions"], rows), errorEl);
  }

  // --- Unassigned trips (requires action) ---

  /**
   * "Nearest: Tom Nguyen, 2.4 mi away" under the driver picker.
   *
   * Fetched per row and only once the queue is on screen, because ranking needs
   * each driver's last position and a dispatcher usually only cares about the
   * top of the list. Selecting the suggestion is one click; the dropdown still
   * holds everyone, because proximity is a hint and the dispatcher knows things
   * the ranking does not.
   */
  function suggestionHint(trip, select) {
    const hint = el("p", { class: "suggest", text: "Finding the nearest driver..." });

    driverSuggestions(trip.id)
      .then((ranked) => {
        const best = ranked[0];
        if (!best) {
          hint.textContent = "No eligible driver for this trip.";
          hint.classList.add("suggest--none");
          return;
        }

        const distance =
          best.miles_away === null ? "position unknown" : `${best.miles_away} mi away`;
        const duty = best.is_available ? "" : " (off duty)";

        clear(hint);
        hint.append(
          el("span", { class: "suggest__label", text: "Nearest: " }),
          el("button", {
            type: "button",
            class: "suggest__pick",
            text: `${best.name} — ${distance}${duty}`,
            onclick: () => {
              select.value = String(best.driver_id);
              select.dispatchEvent(new Event("change"));
              hint.classList.add("suggest--taken");
            },
          })
        );
      })
      .catch(() => {
        // A ranking failure must not take the queue down; the dropdown still works.
        hint.textContent = "";
      });

    return hint;
  }

  function renderQueue(trips, drivers) {
    clear(queueSection);
    queueSection.append(el("h2", { text: "Unassigned trips — requires action" }));
    if (trips.length === 0) {
      showEmpty(queueSection, "No confirmed trips awaiting assignment.");
      return;
    }

    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    // On-duty drivers first: the dropdown opens on someone who can actually go.
    const byDuty = [...drivers].sort((a, b) =>
      a.is_available === b.is_available ? 0 : a.is_available ? -1 : 1
    );

    const rows = trips.map((trip) => {
      const select = el(
        "select",
        {
          onchange: (e) => {
            selectedDrivers[trip.id] = e.target.value;
          },
        },
        byDuty.map((driver) =>
          el("option", {
            value: String(driver.id),
            text: [
              driver.is_available ? "🟢" : "⚪",
              `${driver.first_name} ${driver.last_name}`.trim() || driver.email,
              driver.vehicle_type,
              driver.is_available ? null : "off duty",
            ]
              .filter(Boolean)
              .join(" · "),
          })
        )
      );

      const act = (label, className, fn, successMessage, failureMessage) =>
        el("button", {
          class: `btn ${className}`.trim(),
          text: label,
          onclick: async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            errorEl.hidden = true;
            try {
              await fn();
              showToast(successMessage, { type: "success" });
              load();
            } catch (error) {
              errorEl.textContent = errorMessage(error, failureMessage);
              errorEl.hidden = false;
              button.disabled = false;
            }
          },
        });

      return el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: formatDateTime(trip.scheduled_pickup_time) }),
        el("td", {}, [
          el("div", { text: `${trip.pickup_address} → ${trip.dropoff_address}` }),
          trip.mobility_need
            ? el("span", { class: "chip", text: MOBILITY_LABELS[trip.mobility_need] || trip.mobility_need })
            : null,
          // A trip a driver handed back explains itself, so the next pick is informed.
          trip.decline_reason
            ? el("div", { class: "queue-note", text: `Declined: ${trip.decline_reason}` })
            : null,
          trip.total_cost ? el("div", { class: "queue-note", text: `Fare: ${formatCurrency(trip.total_cost)}` }) : null,
        ]),
        el("td", {}, [select, suggestionHint(trip, select)]),
        el("td", { class: "dispatch-table__actions" }, [
          act(
            "Assign",
            "btn--primary",
            () => assignTrip(trip.id, selectedDrivers[trip.id] || select.value),
            "Driver assigned.",
            "Could not assign that driver (unapproved, incompatible, or already booked)."
          ),
          act(
            "Auto-assign",
            "",
            () => autoAssignTrip(trip.id),
            "Driver auto-assigned.",
            "No available driver found for that trip."
          ),
        ]),
      ]);
    });

    queueSection.append(dataTable(["Pickup", "Route", "Driver", "Actions"], rows), errorEl);
  }

  // --- In flight ---

  function renderInFlight(trips, drivers) {
    clear(inFlightSection);
    inFlightSection.append(el("h2", { text: "In flight" }));
    if (trips.length === 0) {
      showEmpty(inFlightSection, "No trips currently assigned or in progress.");
      return;
    }

    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const rows = trips.map((trip) => {
      // Only a trip the driver hasn't accepted yet can be handed to someone else —
      // the same rule the API enforces.
      const awaitingAcceptance = trip.status === "ASSIGNED" && !trip.accepted_at;

      return el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: formatDateTime(trip.scheduled_pickup_time) }),
        el("td", { text: `${trip.pickup_address} → ${trip.dropoff_address}` }),
        el("td", {}, [
          el("div", { text: trip.assigned_driver_name || "—" }),
          awaitingAcceptance ? el("span", { class: "ops-panel__meta", text: "awaiting acceptance" }) : null,
        ]),
        el("td", {}, [tripStatusBadge(trip.status)]),
        el("td", { class: "dispatch-table__actions" }, awaitingAcceptance ? [reassignControl(trip, drivers, errorEl)] : []),
      ]);
    });

    inFlightSection.append(
      dataTable(["Pickup", "Route", "Driver", "Status", "Actions"], rows),
      errorEl
    );
  }

  /** Hand an unaccepted trip to a different driver (or let the API pick one). */
  function reassignControl(trip, drivers, errorEl) {
    const select = el(
      "select",
      {},
      [el("option", { value: "", text: "Auto — next available" })].concat(
        drivers
          .filter((driver) => driver.id !== trip.assigned_driver)
          .map((driver) =>
            el("option", {
              value: String(driver.id),
              text: [`${driver.first_name} ${driver.last_name}`.trim() || driver.email, driver.vehicle_type]
                .filter(Boolean)
                .join(" · "),
            })
          )
      )
    );

    const button = el("button", {
      class: "btn",
      text: "Reassign",
      onclick: async () => {
        button.disabled = true;
        errorEl.hidden = true;
        try {
          await reassignTrip(trip.id, select.value || undefined);
          showToast("Trip reassigned.", { type: "success" });
          load();
        } catch {
          errorEl.textContent = "Could not reassign that trip (no eligible driver, or it was just accepted).";
          errorEl.hidden = false;
          button.disabled = false;
        }
      },
    });

    return el("div", { class: "reassign" }, [select, button]);
  }

  // --- Live fleet map ---

  // tripId -> { pickup: Marker, vehicle: Marker|null }
  const markers = new Map();
  // tripId -> tracking socket for trips whose driver is streaming location
  const trackers = new Map();
  let framed = false;

  function dropTrip(tripId) {
    const entry = markers.get(tripId);
    if (entry) {
      entry.pickup.setMap(null);
      if (entry.vehicle) entry.vehicle.setMap(null);
      markers.delete(tripId);
    }
    const socket = trackers.get(tripId);
    if (socket) {
      socket.close();
      trackers.delete(tripId);
    }
  }

  // Refreshes can overlap (socket nudge + 30s poll), so map updates run one at a
  // time — otherwise two passes could both add a marker for the same trip.
  let fleetChain = Promise.resolve();
  function syncFleet(trips, onDuty = []) {
    fleetChain = fleetChain.then(() => updateFleet(trips, onDuty)).catch(() => {});
  }

  // Markers for on-duty drivers who aren't currently on a trip, keyed by driver id.
  const idleMarkers = new Map();

  /**
   * Put every on-duty driver on the map, not just the ones mid-trip.
   *
   * A driver between jobs has no trip to hang a marker off, so the board showed
   * an empty map even with four people online -- and those are exactly the
   * drivers a dispatcher is looking for when the next booking comes in.
   */
  function drawIdleDrivers(ctx, onDuty, busyDriverIds) {
    const { maps, map } = ctx;
    const idle = onDuty.filter(
      (row) => row.lat !== null && !row.position_is_stale && !busyDriverIds.has(row.id)
    );
    const present = new Set(idle.map((row) => row.id));

    for (const [id, marker] of [...idleMarkers.entries()]) {
      if (!present.has(id)) {
        marker.setMap(null);
        idleMarkers.delete(id);
      }
    }

    for (const row of idle) {
      const position = { lat: Number(row.lat), lng: Number(row.lng) };
      const existing = idleMarkers.get(row.id);
      if (existing) {
        existing.setPosition(position);
        continue;
      }
      const marker = new maps.Marker({
        position,
        map,
        title: `${row.name} - on duty, free`,
        icon: vehicleDot(maps),
      });
      const info = new maps.InfoWindow();
      marker.addListener("click", () => {
        info.setContent(
          el("div", { class: "fleet-info" }, [
            el("strong", { text: row.name }),
            el("span", { text: [row.vehicle_type, row.vehicle_plate].filter(Boolean).join(" - ") }),
            el("span", { text: "On duty, no trip in flight" }),
            el("span", { text: `Located ${row.position_age_minutes} min ago` }),
          ])
        );
        info.open({ anchor: marker, map });
      });
      idleMarkers.set(row.id, marker);
    }
    return idle.length;
  }

  async function updateFleet(trips, onDuty = []) {
    const plotted = trips.filter((trip) => tripPoint(trip, "pickup"));
    const live = trips.filter((trip) => LIVE_TRIP_STATUSES.includes(trip.status)).length;

    const ctx = await fleet.whenReady;
    if (!ctx) return; // no Maps key -- the panel already says so
    const { maps, map } = ctx;

    const busyDriverIds = new Set(trips.map((trip) => trip.assigned_driver).filter(Boolean));
    const idleCount = drawIdleDrivers(ctx, onDuty, busyDriverIds);

    const tripPart = trips.length
      ? `${plotted.length} trip${plotted.length === 1 ? "" : "s"} in flight, ${live} with a live driver dot`
      : "No trips in flight";
    const idlePart = idleCount
      ? ` - ${idleCount} on-duty driver${idleCount === 1 ? "" : "s"} free and on the map`
      : " - no free drivers sharing a location";
    fleetNote.textContent = `${tripPart}${idlePart}.`;

    const current = new Set(plotted.map((trip) => trip.id));
    for (const tripId of [...markers.keys()]) {
      if (!current.has(tripId)) dropTrip(tripId);
    }

    for (const trip of plotted) {
      const existing = markers.get(trip.id);
      if (existing) {
        // Keep the latest payload so the info window can't quote a stale driver.
        existing.trip = trip;
        continue;
      }
      const marker = new maps.Marker({
        position: tripPoint(trip, "pickup"),
        map,
        title: `${trip.pickup_address} → ${trip.dropoff_address}`,
      });
      const entry = { pickup: marker, vehicle: null, trip };
      markers.set(trip.id, entry);

      const info = new maps.InfoWindow();
      marker.addListener("click", () => {
        info.setContent(
          el("div", { class: "fleet-info" }, [
            el("strong", { text: entry.trip.assigned_driver_name || "Unassigned" }),
            el("span", { text: `${entry.trip.pickup_address} → ${entry.trip.dropoff_address}` }),
            el("span", {}, [tripStatusBadge(entry.trip.status)]),
            el("span", { text: formatDateTime(entry.trip.scheduled_pickup_time) }),
          ])
        );
        info.open({ anchor: marker, map });
      });
    }

    // Follow each streaming driver. Opened in one pass so the sockets share a
    // single access-token refresh.
    for (const trip of plotted) {
      if (trackers.size >= MAX_TRACKED) break;
      if (trackers.has(trip.id) || !LIVE_TRIP_STATUSES.includes(trip.status)) continue;
      trackers.set(
        trip.id,
        openSocket(`trips/${trip.id}/track/`, {
          onJson: (msg) => {
            if (msg.event !== "driver_location") return;
            const entry = markers.get(trip.id);
            if (!entry) return;
            const position = { lat: Number(msg.lat), lng: Number(msg.lng) };
            if (entry.vehicle) entry.vehicle.setPosition(position);
            else
              entry.vehicle = new maps.Marker({
                position,
                map,
                title: `${entry.trip.assigned_driver_name || "Driver"} — live`,
                icon: vehicleDot(maps),
              });
          },
        })
      );
    }

    // Frame the fleet once; after that the dispatcher owns the viewport.
    if (!framed && plotted.length > 0) {
      fitTo(
        maps,
        map,
        plotted.map((trip) => tripPoint(trip, "pickup"))
      );
      framed = true;
    }
  }

  load();

  // Live updates: refresh whenever a trip is booked, assigned, or changes status.
  // The slow poll stays as a fallback if the socket is unavailable (e.g. served
  // without an ASGI server).
  let reloadTimer = null;
  openSocket("dispatch/", {
    onJson: () => {
      // Debounce bursts of updates into a single reload.
      clearTimeout(reloadTimer);
      reloadTimer = setTimeout(load, 300);
    },
  });
  setInterval(load, 30000);
}
