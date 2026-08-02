import {
  requireApprovedDriver,
  listAvailability,
  createAvailability,
  deleteAvailability,
  listTimeOff,
  createTimeOff,
  deleteTimeOff,
} from "../../api/drivers.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { WEEKDAYS, formatDate } from "../../ui/format.js";
import { clearFormErrors, showFormError } from "../../ui/form-errors.js";
import { showToast } from "../../ui/toast.js";

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  const state = { shifts: [], timeOff: [] };

  /** "07:00" from a stored "07:00:00". */
  function hhmm(value) {
    return (value || "").slice(0, 5);
  }

  function weekdayName(value) {
    return WEEKDAYS.find((day) => day.value === value)?.label || `Day ${value}`;
  }

  async function removeShift(shift, button) {
    button.disabled = true;
    try {
      await deleteAvailability(shift.id);
      showToast("Shift removed.", { type: "success" });
      load();
    } catch {
      showToast("Could not remove that shift.", { type: "error" });
      button.disabled = false;
    }
  }

  async function removeTimeOff(period, button) {
    button.disabled = true;
    try {
      await deleteTimeOff(period.id);
      showToast("Time off removed.", { type: "success" });
      load();
    } catch {
      showToast("Could not remove that entry.", { type: "error" });
      button.disabled = false;
    }
  }

  // --- weekly shifts ---

  function shiftList() {
    if (state.shifts.length === 0) {
      return el("p", { class: "empty-note" }, [
        "No shifts recorded, so dispatch treats you as available at any hour. ",
        el("strong", { text: "Add one below to limit when you can be given work." }),
      ]);
    }

    // Grouped by day so a week reads as a week, not as a list of rows.
    const byDay = new Map();
    for (const shift of state.shifts) {
      if (!byDay.has(shift.weekday)) byDay.set(shift.weekday, []);
      byDay.get(shift.weekday).push(shift);
    }

    return el(
      "ul",
      { class: "shift-list" },
      WEEKDAYS.map((day) => {
        const shifts = byDay.get(day.value) || [];
        return el("li", { class: `shift-day${shifts.length ? "" : " shift-day--empty"}` }, [
          el("span", { class: "shift-day__name", text: day.label }),
          shifts.length
            ? el(
                "span",
                { class: "shift-day__windows" },
                shifts.map((shift) =>
                  el("span", { class: "shift-chip" }, [
                    `${hhmm(shift.start_time)}–${hhmm(shift.end_time)}`,
                    el("button", {
                      type: "button",
                      class: "shift-chip__remove",
                      "aria-label": `Remove ${day.label} ${hhmm(shift.start_time)} shift`,
                      text: "×",
                      onclick: (event) => removeShift(shift, event.currentTarget),
                    }),
                  ])
                )
              )
            : el("span", { class: "shift-day__none", text: "Not working" }),
        ]);
      })
    );
  }

  function shiftForm() {
    const weekday = el(
      "select",
      { id: "shift-weekday" },
      WEEKDAYS.map((day) => el("option", { value: String(day.value), text: day.label }))
    );
    const start = el("input", { type: "time", id: "shift-start", value: "07:00", required: "required" });
    const end = el("input", { type: "time", id: "shift-end", value: "15:30", required: "required" });
    const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Add shift" });
    const fields = { weekday, start_time: start, end_time: end };

    return el(
      "form",
      {
        class: "inline-form",
        onsubmit: async (event) => {
          event.preventDefault();
          clearFormErrors(errorEl, fields);
          submit.disabled = true;
          try {
            await createAvailability({
              weekday: Number(weekday.value),
              start_time: start.value,
              end_time: end.value,
            });
            showToast("Shift added.", { type: "success" });
            load();
          } catch (error) {
            showFormError(errorEl, error, fields);
            submit.disabled = false;
          }
        },
      },
      [
        el("div", { class: "field-pair" }, [
          el("label", { class: "field-row" }, ["Day", weekday]),
          el("label", { class: "field-row" }, ["From", start]),
          el("label", { class: "field-row" }, ["To", end]),
        ]),
        submit,
        errorEl,
      ]
    );
  }

  // --- time off ---

  function timeOffList() {
    if (state.timeOff.length === 0) {
      return el("p", { class: "empty-note", text: "No time off booked." });
    }
    return el(
      "ul",
      { class: "timeoff-list" },
      state.timeOff.map((period) =>
        el("li", { class: "timeoff" }, [
          el("span", { class: "timeoff__dates" }, [
            formatDate(period.start_date),
            period.end_date !== period.start_date ? ` to ${formatDate(period.end_date)}` : "",
          ]),
          period.reason ? el("span", { class: "timeoff__reason", text: period.reason }) : null,
          el("button", {
            type: "button",
            class: "btn btn--ghost btn--small",
            text: "Remove",
            onclick: (event) => removeTimeOff(period, event.currentTarget),
          }),
        ])
      )
    );
  }

  function timeOffForm() {
    const today = new Date().toISOString().slice(0, 10);
    const start = el("input", { type: "date", id: "off-start", min: today, required: "required" });
    const end = el("input", { type: "date", id: "off-end", min: today, required: "required" });
    const reason = el("input", { type: "text", id: "off-reason", placeholder: "Optional" });
    const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Book time off" });
    const fields = { start_date: start, end_date: end, reason };

    // Picking a start date that lands after the end date is the commonest slip;
    // move the end forward with it rather than waiting to reject the submit.
    start.addEventListener("change", () => {
      end.min = start.value;
      if (!end.value || end.value < start.value) end.value = start.value;
    });

    return el(
      "form",
      {
        class: "inline-form",
        onsubmit: async (event) => {
          event.preventDefault();
          clearFormErrors(errorEl, fields);
          submit.disabled = true;
          try {
            await createTimeOff({
              start_date: start.value,
              end_date: end.value,
              reason: reason.value.trim(),
            });
            showToast("Time off booked.", { type: "success" });
            load();
          } catch (error) {
            showFormError(errorEl, error, fields);
            submit.disabled = false;
          }
        },
      },
      [
        el("div", { class: "field-pair" }, [
          el("label", { class: "field-row" }, ["First day off", start]),
          el("label", { class: "field-row" }, ["Last day off", end]),
          el("label", { class: "field-row" }, ["Reason", reason]),
        ]),
        submit,
        errorEl,
      ]
    );
  }

  async function load() {
    showLoading(content, "Loading your calendar...");
    try {
      const [shifts, timeOff] = await Promise.all([listAvailability(), listTimeOff()]);
      state.shifts = shifts.results || [];
      state.timeOff = timeOff.results || [];

      clear(content);
      content.append(
        el("section", { class: "settings-card" }, [
          el("h2", { text: "Weekly shifts" }),
          el("p", {
            class: "section-lead",
            text: "Auto-assignment only offers you trips that start inside one of these windows.",
          }),
          shiftList(),
          shiftForm(),
        ]),
        el("section", { class: "settings-card" }, [
          el("h2", { text: "Time off" }),
          el("p", {
            class: "section-lead",
            text: "Days you're unavailable whatever your usual shifts say. Both dates included.",
          }),
          timeOffList(),
          timeOffForm(),
        ])
      );
    } catch {
      showError(content, "Could not load your calendar.");
    }
  }

  load();
}
