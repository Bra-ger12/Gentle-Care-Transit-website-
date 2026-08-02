import { requireRole } from "../../api/auth.js";
import {
  getSettings,
  updateSettings,
  listServiceAreas,
  createServiceArea,
  updateServiceArea,
  deleteServiceArea,
  listPlaces,
} from "../../api/operations.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { clearFormErrors, showFormError } from "../../ui/form-errors.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  const state = { settings: null, areas: [], places: [] };

  // --- service area ---

  function areaDescription(area) {
    if (area.kind === "PLACE") return `Town: ${area.place}`;
    return `Within ${Number(area.radius_miles)} miles of ${area.center_lat}, ${area.center_lng}`;
  }

  async function toggleArea(area, button) {
    button.disabled = true;
    try {
      await updateServiceArea(area.id, { is_active: !area.is_active });
      showToast(area.is_active ? "Area switched off." : "Area switched on.", { type: "success" });
      load();
    } catch {
      showToast("Could not change that area.", { type: "error" });
      button.disabled = false;
    }
  }

  async function removeArea(area, button) {
    button.disabled = true;
    try {
      await deleteServiceArea(area.id);
      showToast("Area removed.", { type: "success" });
      load();
    } catch {
      showToast("Could not remove that area.", { type: "error" });
      button.disabled = false;
    }
  }

  function areaList() {
    const active = state.areas.filter((area) => area.is_active);

    if (state.areas.length === 0) {
      return el("p", { class: "queue-note" }, [
        el("strong", { text: "No boundary set. " }),
        "Any address in the country is bookable. Add an area below to restrict it.",
      ]);
    }

    return el("div", {}, [
      active.length === 0
        ? el("p", { class: "queue-note", text: "Every area is switched off, so nothing is restricted." })
        : null,
      el(
        "ul",
        { class: "area-list" },
        state.areas.map((area) =>
          el("li", { class: `area${area.is_active ? "" : " area--off"}` }, [
            el("div", { class: "area__main" }, [
              el("span", { class: "area__name", text: area.name }),
              el("span", { class: "area__detail", text: areaDescription(area) }),
            ]),
            el("div", { class: "area__actions" }, [
              el("button", {
                type: "button",
                class: "btn btn--ghost btn--small",
                text: area.is_active ? "Switch off" : "Switch on",
                onclick: (event) => toggleArea(area, event.currentTarget),
              }),
              el("button", {
                type: "button",
                class: "btn btn--ghost btn--small",
                text: "Remove",
                onclick: (event) => removeArea(area, event.currentTarget),
              }),
            ]),
          ])
        )
      ),
    ]);
  }

  function areaForm() {
    const name = el("input", { type: "text", id: "area-name", required: "required" });
    const kind = el("select", { id: "area-kind" }, [
      el("option", { value: "PLACE", text: "A town or city" }),
      el("option", { value: "RADIUS", text: "A radius around a point" }),
    ]);
    const place = el(
      "select",
      { id: "area-place" },
      state.places.map((option) => el("option", { value: option.name, text: option.name }))
    );
    const lat = el("input", { type: "number", step: "0.000001", id: "area-lat", value: "46.8083" });
    const lng = el("input", { type: "number", step: "0.000001", id: "area-lng", value: "-100.7837" });
    const radius = el("input", { type: "number", step: "0.1", min: "0.1", id: "area-radius", value: "40" });

    const placeFields = el("div", { class: "field-row" }, ["Town", place]);
    const radiusFields = el("div", { class: "field-pair", hidden: "hidden" }, [
      el("label", { class: "field-row" }, ["Centre latitude", lat]),
      el("label", { class: "field-row" }, ["Centre longitude", lng]),
      el("label", { class: "field-row" }, ["Radius (miles)", radius]),
    ]);

    // Naming the town is also the sensible default label, so typing it twice
    // isn't required for the common case.
    place.addEventListener("change", () => {
      if (!name.value.trim()) name.value = place.value;
    });

    kind.addEventListener("change", () => {
      const isPlace = kind.value === "PLACE";
      placeFields.hidden = !isPlace;
      radiusFields.hidden = isPlace;
    });

    const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Add area" });
    const fields = { name, kind, place, center_lat: lat, center_lng: lng, radius_miles: radius };

    return el(
      "form",
      {
        class: "inline-form",
        onsubmit: async (event) => {
          event.preventDefault();
          clearFormErrors(errorEl, fields);
          submit.disabled = true;

          const payload =
            kind.value === "PLACE"
              ? { name: name.value.trim() || place.value, kind: "PLACE", place: place.value }
              : {
                  name: name.value.trim(),
                  kind: "RADIUS",
                  center_lat: lat.value,
                  center_lng: lng.value,
                  radius_miles: radius.value,
                };

          try {
            await createServiceArea(payload);
            showToast("Service area added.", { type: "success" });
            load();
          } catch (error) {
            showFormError(errorEl, error, fields);
            submit.disabled = false;
          }
        },
      },
      [
        el("label", { class: "field-row" }, ["Name", name]),
        el("label", { class: "field-row" }, ["Kind", kind]),
        placeFields,
        radiusFields,
        submit,
        errorEl,
      ]
    );
  }

  // --- policy + templates ---

  function numberField(id, label, value, hint, attrs = {}) {
    const input = el("input", { type: "number", min: "0", id, value: String(value), ...attrs });
    return {
      input,
      row: el("div", { class: "setting-row" }, [
        el("label", { class: "field-row", for: id }, [label, input]),
        hint ? el("p", { class: "setting-row__hint", text: hint }) : null,
      ]),
    };
  }

  function checkboxField(id, label, checked, hint) {
    const input = el("input", { type: "checkbox", id, ...(checked ? { checked: "checked" } : {}) });
    return {
      input,
      row: el("div", { class: "setting-row" }, [
        el("label", { class: "checkbox-row", for: id }, [input, label]),
        hint ? el("p", { class: "setting-row__hint", text: hint }) : null,
      ]),
    };
  }

  function textareaField(id, label, value, hint) {
    const input = el("textarea", { id, rows: "2", placeholder: "Leave blank to use the built-in wording" });
    input.value = value || "";
    return {
      input,
      row: el("div", { class: "setting-row" }, [
        el("label", { class: "field-row", for: id }, [label, input]),
        hint ? el("p", { class: "setting-row__hint", text: hint }) : null,
      ]),
    };
  }

  function policyForm() {
    const settings = state.settings;

    const enforce = checkboxField(
      "enforce-area",
      "Only accept bookings inside the service area",
      settings.enforce_service_area,
      "Off means the areas above are ignored and anywhere is bookable."
    );
    const verify = checkboxField(
      "require-verified",
      "Riders must confirm their email before booking",
      settings.require_verified_email_to_book,
      "Turn off if you take bookings from people without reliable email."
    );
    const cutoff = numberField(
      "cutoff-hours",
      "Cancellation / reschedule cutoff (hours)",
      settings.cancellation_cutoff_hours,
      "How long before pickup a rider can still change their trip. Admins are never blocked.",
      { max: "168" }
    );
    const lead = numberField(
      "lead-minutes",
      "Minimum booking notice (minutes)",
      settings.booking_lead_time_minutes,
      "0 lets a rider book for right now."
    );
    const wait = numberField(
      "wait-minutes",
      "Driver wait before a no-show (minutes)",
      settings.no_show_wait_minutes,
      "The driver's screen counts this down and only then unlocks the no-show button.",
      { max: "120" }
    );

    const confirmed = textareaField(
      "tpl-confirmed",
      "Trip confirmed",
      settings.template_trip_confirmed,
      "Placeholders: {when} {route} {pickup} {dropoff} {rider} {driver}"
    );
    const assigned = textareaField(
      "tpl-assigned",
      "Driver assigned",
      settings.template_driver_assigned,
      "Sent to the driver when dispatch assigns them a trip."
    );
    const enRoute = textareaField(
      "tpl-enroute",
      "Driver en route",
      settings.template_driver_en_route,
      "Sent to the rider when their driver sets off."
    );
    const reminder = textareaField(
      "tpl-reminder",
      "Appointment reminder",
      settings.template_trip_reminder,
      "Sent ahead of the pickup by the reminder sweep."
    );

    const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Save settings" });
    const fields = {
      enforce_service_area: enforce.input,
      require_verified_email_to_book: verify.input,
      cancellation_cutoff_hours: cutoff.input,
      booking_lead_time_minutes: lead.input,
      no_show_wait_minutes: wait.input,
      template_trip_confirmed: confirmed.input,
      template_driver_assigned: assigned.input,
      template_driver_en_route: enRoute.input,
      template_trip_reminder: reminder.input,
    };

    return el(
      "form",
      {
        class: "inline-form",
        onsubmit: async (event) => {
          event.preventDefault();
          clearFormErrors(errorEl, fields);
          submit.disabled = true;
          try {
            await updateSettings({
              enforce_service_area: enforce.input.checked,
              require_verified_email_to_book: verify.input.checked,
              cancellation_cutoff_hours: Number(cutoff.input.value),
              booking_lead_time_minutes: Number(lead.input.value),
              no_show_wait_minutes: Number(wait.input.value),
              template_trip_confirmed: confirmed.input.value,
              template_driver_assigned: assigned.input.value,
              template_driver_en_route: enRoute.input.value,
              template_trip_reminder: reminder.input.value,
            });
            showToast("Settings saved.", { type: "success" });
            load();
          } catch (error) {
            showFormError(errorEl, error, fields);
            submit.disabled = false;
          }
        },
      },
      [
        el("h3", { class: "setting-group", text: "Booking rules" }),
        enforce.row,
        verify.row,
        cutoff.row,
        lead.row,
        wait.row,
        el("h3", { class: "setting-group", text: "Message wording" }),
        el("p", {
          class: "section-lead",
          text: "Leave a box empty to keep the wording built into the app. A typo in a placeholder shows as literal text rather than stopping the message.",
        }),
        confirmed.row,
        assigned.row,
        enRoute.row,
        reminder.row,
        submit,
        errorEl,
      ]
    );
  }

  async function load() {
    showLoading(content, "Loading settings...");
    try {
      const [settings, areas, places] = await Promise.all([
        getSettings(),
        listServiceAreas(),
        listPlaces().catch(() => []),
      ]);
      state.settings = settings;
      state.areas = areas.results || [];
      state.places = places || [];

      clear(content);
      content.append(
        el("section", { class: "settings-card" }, [
          el("h2", { text: "Service area" }),
          el("p", {
            class: "section-lead",
            text: "A trip is bookable when both ends fall inside at least one active area. A county is either its towns listed individually, or a radius around its centre.",
          }),
          areaList(),
          areaForm(),
        ]),
        el("section", { class: "settings-card" }, [el("h2", { text: "Policy" }), policyForm()])
      );
    } catch {
      showError(content, "Could not load settings.");
    }
  }

  load();
}
