import { createTrip, createRecurringSeries, estimateTripCost, listServices } from "../../api/trips.js";
import { el } from "../../ui/dom.js";
import { formatCurrency, MOBILITY_NEEDS, WEEKDAYS } from "../../ui/format.js";
import { clearFormErrors, showFormError } from "../../ui/form-errors.js";

/**
 * The booking form, shared by a rider booking for themselves and an admin
 * taking the same booking over the phone.
 *
 * One component rather than two, because the two flows differ in exactly one
 * respect -- who the trip is for -- and every other rule (round trips,
 * will-call, escorts, the service area, the lead time) has to behave
 * identically whichever door the booking came through. Two copies would drift.
 */

/** `datetime-local` wants local wall-clock text, not an ISO instant. */
function localDateTimeValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function field(labelText, input, hint) {
  return el("div", { class: "book-field" }, [
    el("label", { class: "field-row", for: input.id }, [labelText, input]),
    hint ? el("p", { class: "book-field__hint", text: hint }) : null,
  ]);
}

export function bookingForm({ riders = null, policy = null, onBooked, presetDropoff = "" } = {}) {
  const isPhoneBooking = riders !== null;

  // --- who ---
  const riderSelect = isPhoneBooking
    ? el(
        "select",
        { id: "book-rider", required: "required" },
        [el("option", { value: "", text: "Choose a rider..." })].concat(
          riders.map((rider) =>
            el("option", {
              value: String(rider.id),
              text: `${rider.name}${rider.phone ? ` · ${rider.phone}` : ""}`,
            })
          )
        )
      )
    : null;

  // --- where ---
  const pickup = el("input", { type: "text", id: "book-pickup", required: "required", autocomplete: "off" });
  const dropoff = el("input", {
    type: "text",
    id: "book-dropoff",
    required: "required",
    autocomplete: "off",
    value: presetDropoff,
  });
  const serviceSelect = el("select", { id: "book-service", required: "required" }, [
    el("option", { value: "", text: "Loading services..." }),
  ]);

  // --- when ---
  const isRecurring = el("input", { type: "checkbox", id: "book-recurring" });
  const pickupDateTime = el("input", { type: "datetime-local", id: "book-when", required: "required" });
  const startDate = el("input", { type: "date", id: "book-start" });
  const pickupTime = el("input", { type: "time", id: "book-time" });
  const endDate = el("input", { type: "date", id: "book-end" });
  const weekdayPicker = el(
    "div",
    { class: "weekday-picker", id: "book-weekdays" },
    WEEKDAYS.map((day) =>
      el("label", { class: "weekday-picker__option" }, [
        el("input", { type: "checkbox", value: String(day.value) }),
        day.label.slice(0, 3),
      ])
    )
  );

  // A booking needs at least the configured notice; pre-fill something valid so
  // the first submit isn't a rejection.
  const leadMinutes = policy?.booking_lead_time_minutes ?? 60;
  const earliest = new Date(Date.now() + (leadMinutes + 30) * 60000);
  pickupDateTime.value = localDateTimeValue(earliest);
  pickupDateTime.min = localDateTimeValue(new Date(Date.now() + leadMinutes * 60000));
  startDate.value = earliest.toISOString().slice(0, 10);
  startDate.min = new Date().toISOString().slice(0, 10);
  pickupTime.value = "09:00";

  // --- return ---
  const tripTypeOptions = [
    { value: "ONE_WAY", label: "One way" },
    { value: "ROUND_TRIP", label: "Round trip" },
  ];
  const tripTypeInputs = tripTypeOptions.map((option, index) =>
    el("input", {
      type: "radio",
      name: "trip_type",
      value: option.value,
      checked: index === 0 ? "checked" : undefined,
    })
  );
  const tripType = el(
    "div",
    { id: "book-type", class: "trip-type-options", role: "radiogroup", tabindex: "0" },
    tripTypeOptions.map((option, index) =>
      el("label", { class: "trip-type-option" }, [
        tripTypeInputs[index],
        el("span", { text: option.label }),
      ])
    )
  );
  const returnMode = el("select", { id: "book-return-mode" }, [
    el("option", { value: "TIME", text: "A set return time" }),
    el("option", { value: "WILL_CALL", text: "Will-call — the rider phones when they're ready" }),
  ]);
  const returnTime = el("input", { type: "datetime-local", id: "book-return-when" });

  // --- who else, and what they need ---
  const mobility = el(
    "select",
    { id: "book-mobility" },
    [el("option", { value: "", text: "None" })].concat(
      MOBILITY_NEEDS.map((need) => el("option", { value: need.value, text: need.label }))
    )
  );
  const escorts = el("input", { type: "number", id: "book-escorts", min: "0", max: "4", value: "0" });
  const notes = el("textarea", { id: "book-notes", rows: "3" });

  const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
  const submitBtn = el("button", { type: "submit", class: "btn btn--primary", text: "Book trip" });
  const estimateTitle = el("p", { class: "fare-estimate__label", text: "Estimated total" });
  const estimateAmount = el("p", { class: "fare-estimate__amount", text: "--" });
  const estimateMeta = el("p", {
    class: "fare-estimate__meta",
    text: "Choose a service and enter both addresses to see the fare.",
  });
  const estimateBox = el("section", { class: "fare-estimate", "aria-live": "polite" }, [
    estimateTitle,
    estimateAmount,
    estimateMeta,
  ]);

  function selectedTripType() {
    return tripTypeInputs.find((input) => input.checked)?.value || "ONE_WAY";
  }

  function selectedService() {
    return serviceSelect.value;
  }

  // --- panels that show and hide together ---
  const oneTimeFields = el("div", { class: "collapsible is-open" }, [
    field("Pickup date & time", pickupDateTime),
  ]);
  const recurringFields = el("div", { class: "collapsible" }, [
    field("First pickup date", startDate),
    field("Pickup time", pickupTime),
    el("div", { class: "book-field" }, [el("label", { text: "Repeat on" }), weekdayPicker]),
    field("Stop repeating after (optional)", endDate),
  ]);
  const returnTimeField = field("Return pickup time", returnTime);
  const returnFields = el("div", { class: "collapsible" }, [
    field("Getting home", returnMode),
    returnTimeField,
    el("p", {
      class: "book-field__hint",
      text: "A round trip is booked as two rides. Will-call leaves the second one open until the rider calls.",
    }),
  ]);

  function syncPanels() {
    const recurring = isRecurring.checked;
    const roundTrip = selectedTripType() === "ROUND_TRIP" && !recurring;

    oneTimeFields.classList.toggle("is-open", !recurring);
    recurringFields.classList.toggle("is-open", recurring);
    returnFields.classList.toggle("is-open", roundTrip);
    // A repeating booking is one leg per occurrence; a return on top of that is
    // a second series, which is a different thing to set up.
    tripTypeInputs.forEach((input) => {
      input.disabled = recurring;
    });
    tripType.classList.toggle("is-disabled", recurring);

    // Collapsed inputs stay in the layout for the reveal animation, so their
    // `required` flag has to track visibility or submit blocks on a hidden field.
    pickupDateTime.required = !recurring;
    startDate.required = recurring;
    pickupTime.required = recurring;
    returnTime.required = roundTrip && returnMode.value === "TIME";
    returnTimeField.hidden = returnMode.value !== "TIME";
    updateEstimate();
  }

  function setEstimatePending(message) {
    estimateBox.classList.remove("fare-estimate--error");
    estimateAmount.textContent = "--";
    estimateMeta.textContent = message;
  }

  function setEstimateError(message) {
    estimateBox.classList.add("fare-estimate--error");
    estimateAmount.textContent = "--";
    estimateMeta.textContent = message;
  }

  function estimatePayload() {
    const payload = {
      service_id: selectedService(),
      pickup_address: pickup.value.trim(),
      dropoff_address: dropoff.value.trim(),
      trip_type: isRecurring.checked ? "ONE_WAY" : selectedTripType(),
    };
    return payload.service_id && payload.pickup_address && payload.dropoff_address ? payload : null;
  }

  let estimateTimer = null;
  let estimateSeq = 0;
  function updateEstimate() {
    clearTimeout(estimateTimer);
    // Invalidate in-flight responses immediately, including when an address is
    // cleared before the next debounced request starts.
    const seq = ++estimateSeq;
    const payload = estimatePayload();
    if (!payload) {
      setEstimatePending("Choose a service and enter both addresses to see the fare.");
      return;
    }

    estimateTimer = setTimeout(async () => {
      setEstimatePending("Calculating fare...");
      try {
        const estimate = await estimateTripCost(payload);
        if (seq !== estimateSeq) return;
        estimateBox.classList.remove("fare-estimate--error");
        estimateAmount.textContent = formatCurrency(estimate.total_cost);
        const distance = estimate.distance_km ? `${Number(estimate.distance_km).toFixed(2)} km` : "distance pending";
        const perKm = formatCurrency(estimate.cost_per_km);
        const suffix = estimate.leg_count > 1 ? `, ${estimate.leg_count} legs` : "";
        estimateMeta.textContent = `${estimate.service_name}: ${distance} at ${perKm}/km${suffix}.`;
      } catch {
        if (seq !== estimateSeq) return;
        setEstimateError("Could not calculate this route. Check the addresses or call dispatch.");
      }
    }, 450);
  }

  async function loadServices() {
    try {
      const payload = await listServices();
      const services = payload.results || payload;
      const active = services.filter((service) => service.is_active !== false);
      serviceSelect.replaceChildren(
        el("option", { value: "", text: "Choose a service..." }),
        ...active.map((service) =>
          el("option", {
            value: service.id,
            text: `${service.name} - ${formatCurrency(service.cost_per_km)}/km`,
          })
        )
      );
      if (active.length === 1) serviceSelect.value = active[0].id;
      updateEstimate();
    } catch {
      serviceSelect.replaceChildren(el("option", { value: "", text: "Services unavailable" }));
      setEstimateError("Could not load service prices. Try again or call dispatch.");
    }
  }

  isRecurring.addEventListener("change", syncPanels);
  tripTypeInputs.forEach((input) => input.addEventListener("change", syncPanels));
  returnMode.addEventListener("change", syncPanels);
  [pickup, dropoff, serviceSelect].forEach((input) => input.addEventListener("input", updateEstimate));
  serviceSelect.addEventListener("change", updateEstimate);
  pickupDateTime.addEventListener("change", () => {
    // The return can't precede the outbound; keep the picker honest.
    if (pickupDateTime.value) {
      returnTime.min = pickupDateTime.value;
      if (!returnTime.value || returnTime.value <= pickupDateTime.value) {
        const outbound = new Date(pickupDateTime.value);
        returnTime.value = localDateTimeValue(new Date(outbound.getTime() + 2 * 60 * 60 * 1000));
      }
    }
  });

  const fields = {
    rider_id: riderSelect,
    pickup_address: pickup,
    dropoff_address: dropoff,
    scheduled_pickup_time: pickupDateTime,
    return_pickup_time: returnTime,
    trip_type: tripType,
    escort_count: escorts,
    mobility_need: mobility,
    notes,
    service_id: serviceSelect,
    start_date: startDate,
    pickup_time: pickupTime,
    end_date: endDate,
    weekdays: weekdayPicker,
  };

  async function submit(event) {
    event.preventDefault();
    clearFormErrors(errorEl, fields);
    submitBtn.disabled = true;
    submitBtn.textContent = "Booking...";

    const shared = {
      pickup_address: pickup.value.trim(),
      dropoff_address: dropoff.value.trim(),
      service_id: selectedService(),
      mobility_need: mobility.value || undefined,
      notes: notes.value.trim() || undefined,
    };

    try {
      if (isRecurring.checked) {
        const weekdays = [...weekdayPicker.querySelectorAll("input:checked")].map((box) =>
          Number(box.value)
        );
        await createRecurringSeries({
          ...shared,
          pickup_time: `${pickupTime.value}:00`,
          weekdays,
          start_date: startDate.value,
          end_date: endDate.value || null,
        });
      } else {
        const payload = {
          ...shared,
          scheduled_pickup_time: new Date(pickupDateTime.value).toISOString(),
          escort_count: Number(escorts.value) || 0,
          trip_type: selectedTripType(),
        };
        if (riderSelect) payload.rider_id = Number(riderSelect.value);
        if (selectedTripType() === "ROUND_TRIP") {
          if (returnMode.value === "WILL_CALL") payload.return_is_will_call = true;
          else payload.return_pickup_time = new Date(returnTime.value).toISOString();
        }
        await createTrip(payload);
      }
      onBooked?.();
    } catch (error) {
      showFormError(errorEl, error, fields);
      submitBtn.disabled = false;
      submitBtn.textContent = "Book trip";
    }
  }

  const form = el("form", { class: "auth-form book-form", onsubmit: submit }, [
    riderSelect ? field("Rider", riderSelect, "Who is this trip for?") : null,
    field("Pickup address", pickup, "Include the town, e.g. 1420 Boulevard Ave, Bismarck, ND"),
    field("Drop-off address", dropoff),
    field("Service", serviceSelect, "The selected service locks the fare for this booking."),
    estimateBox,
    el("label", { class: "checkbox-row" }, [isRecurring, "Repeat this trip weekly"]),
    oneTimeFields,
    recurringFields,
    field("Trip type", tripType),
    returnFields,
    field("Mobility need", mobility),
    field("Travelling companions", escorts, "Family, aide or interpreter riding along. They need seats."),
    field("Notes for the driver", notes),
    submitBtn,
    errorEl,
  ]);

  syncPanels();
  loadServices();
  return form;
}
