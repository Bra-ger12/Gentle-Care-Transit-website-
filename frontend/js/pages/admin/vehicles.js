import { requireRole } from "../../api/auth.js";
import { listDrivers, updateDriverVehicle } from "../../api/drivers.js";
import { listInspections } from "../../api/fleet.js";
import { listTrips } from "../../api/trips.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { licenseBadge } from "../../ui/badges.js";
import { ratingSummary } from "../../ui/rating.js";
import { formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const VEHICLE_TYPES = [
  ["", "Unspecified"],
  ["SEDAN", "Sedan"],
  ["WHEELCHAIR_VAN", "Wheelchair van"],
  ["STRETCHER_VAN", "Stretcher van"],
];

const TYPE_LABELS = Object.fromEntries(VEHICLE_TYPES);
const IN_FLIGHT = "ASSIGNED,EN_ROUTE,ARRIVED,PICKED_UP";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  /** Latest inspection per driver, so each van shows its current road-worthiness. */
  function latestByDriver(inspections) {
    const latest = new Map();
    for (const inspection of inspections) {
      const seen = latest.get(inspection.driver);
      if (!seen || new Date(inspection.performed_at) > new Date(seen.performed_at)) {
        latest.set(inspection.driver, inspection);
      }
    }
    return latest;
  }

  function inspectionLine(inspection) {
    if (!inspection) {
      return el("p", { class: "ops-panel__note", text: "No vehicle check on file." });
    }
    if (!inspection.safe_to_operate) {
      return el("p", { class: "record__reason" }, [
        `Grounded — marked NOT safe to operate ${formatDateTime(inspection.performed_at)}. `,
        inspection.defect_notes,
      ]);
    }
    if (inspection.needs_attention) {
      return el("p", { class: "record__reason", text: `Defects awaiting review: ${inspection.defect_notes}` });
    }
    return el("p", {
      class: "ops-panel__note",
      text: `Last checked ${formatDateTime(inspection.performed_at)} — no open defects.`,
    });
  }

  function vehicleCard(driver, { inspection, duplicatePlate, activeTrips }) {
    const typeSelect = el(
      "select",
      {},
      VEHICLE_TYPES.map(([value, label]) =>
        el("option", { value, selected: (driver.vehicle_type || "") === value ? "selected" : undefined, text: label })
      )
    );
    const plateInput = el("input", { type: "text", value: driver.vehicle_plate || "", placeholder: "e.g. ND 4821-K" });
    const capacityInput = el("input", {
      type: "number",
      min: "1",
      value: driver.vehicle_capacity ?? "",
      placeholder: "seats",
    });
    const errorEl = el("p", { class: "form-error", hidden: "hidden" });

    const saveBtn = el("button", {
      class: "btn btn--primary",
      text: "Save vehicle",
      onclick: async () => {
        errorEl.hidden = true;
        saveBtn.disabled = true;
        try {
          await updateDriverVehicle(driver.id, {
            vehicle_type: typeSelect.value,
            vehicle_plate: plateInput.value.trim(),
            vehicle_capacity: capacityInput.value ? Number(capacityInput.value) : null,
          });
          showToast("Vehicle updated.", { type: "success" });
          load();
        } catch {
          errorEl.textContent = "Could not save this vehicle.";
          errorEl.hidden = false;
          saveBtn.disabled = false;
        }
      },
    });

    const name = `${driver.first_name} ${driver.last_name}`.trim() || driver.email;
    const grounded = inspection && !inspection.safe_to_operate;

    const card = el("article", { class: `van${grounded ? " van--grounded" : ""}` }, [
      el("div", { class: "van__head" }, [
        el("span", { class: "van__plate", text: driver.vehicle_plate || "No plate" }),
        el("span", { class: "chip", text: TYPE_LABELS[driver.vehicle_type] || "Unspecified" }),
      ]),
      el("p", { class: "van__driver" }, [
        el("span", { class: `avail-dot ${driver.is_available ? "avail-dot--on" : "avail-dot--off"}` }),
        el("span", { text: name }),
        driver.is_approved ? null : el("span", { class: "chip chip--alert", text: "Not approved" }),
      ]),
      el("p", {
        class: "van__load",
        text: activeTrips > 0 ? `${activeTrips} trip${activeTrips === 1 ? "" : "s"} in flight` : "No trips in flight",
      }),
      driver.ratings_count ? el("p", {}, [ratingSummary(driver.average_rating, driver.ratings_count)]) : null,
      licenseBadge(driver),
      inspectionLine(inspection),
    ]);

    if (!driver.vehicle_plate) {
      card.append(
        el("p", { class: "record__reason", text: "No plate recorded — this van can't be told apart on the board." })
      );
    } else if (duplicatePlate) {
      card.append(
        el("p", {
          class: "record__reason",
          text: `Plate ${driver.vehicle_plate} is on more than one driver — dispatch can't tell these vans apart.`,
        })
      );
    }
    if (!driver.vehicle_type) {
      card.append(
        el("p", {
          class: "record__reason",
          text: "No vehicle type — auto-assignment can't match this van to a wheelchair or stretcher trip.",
        })
      );
    }

    card.append(
      el("div", { class: "van__form" }, [
        el("div", { class: "field-row" }, [el("label", { text: "Vehicle type" }), typeSelect]),
        el("div", { class: "field-row" }, [el("label", { text: "Plate" }), plateInput]),
        el("div", { class: "field-row" }, [el("label", { text: "Capacity (seats)" }), capacityInput]),
        el("div", { class: "van__actions" }, [saveBtn]),
        errorEl,
      ])
    );
    return card;
  }

  async function load() {
    showLoading(content, "Loading the fleet...");
    try {
      const [drivers, inspections, inFlight] = await Promise.all([
        listDrivers(),
        listInspections().catch(() => ({ results: [] })),
        listTrips(1, IN_FLIGHT).catch(() => ({ results: [] })),
      ]);
      clear(content);

      if (drivers.results.length === 0) {
        showEmpty(content, "No drivers on file — a van is recorded against the driver who operates it.");
        return;
      }

      const latest = latestByDriver(inspections.results || []);
      const plateCounts = new Map();
      for (const d of drivers.results) {
        const plate = (d.vehicle_plate || "").trim().toUpperCase();
        if (plate) plateCounts.set(plate, (plateCounts.get(plate) || 0) + 1);
      }
      const load_ = new Map();
      for (const trip of inFlight.results || []) {
        if (trip.assigned_driver) load_.set(trip.assigned_driver, (load_.get(trip.assigned_driver) || 0) + 1);
      }

      const grounded = drivers.results.filter((d) => {
        const i = latest.get(d.id);
        return i && !i.safe_to_operate;
      }).length;

      content.append(
        el("p", { class: "section-lead" }, [
          `${drivers.results.length} van${drivers.results.length === 1 ? "" : "s"} on file`,
          grounded > 0 ? ` · ${grounded} grounded by a failed vehicle check` : " · none grounded",
          ". ",
          el("a", { href: "/admin/inspections.html", text: "Vehicle inspections" }),
        ]),
        el(
          "div",
          { class: "van-grid" },
          drivers.results.map((driver) =>
            vehicleCard(driver, {
              inspection: latest.get(driver.id),
              duplicatePlate: (plateCounts.get((driver.vehicle_plate || "").trim().toUpperCase()) || 0) > 1,
              activeTrips: load_.get(driver.id) || 0,
            })
          )
        )
      );
    } catch {
      showError(content, "Could not load the fleet.");
    }
  }

  load();
}
