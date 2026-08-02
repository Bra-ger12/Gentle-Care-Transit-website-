import { requireRole } from "../../api/auth.js";
import {
  getKpiSummary,
  getRevenueByMonth,
  getDriverPerformance,
  downloadReport,
  REPORT_EXPORTS,
} from "../../api/reports.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { formatCurrency, formatMonthLabel } from "../../ui/format.js";
import { dataTable } from "../../ui/dom.js";
import { errorMessage } from "../../ui/form-errors.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  /**
   * CSV downloads.
   *
   * Fetched as a blob and handed to a temporary object URL rather than linked
   * directly: the API is authenticated with a bearer token held in memory, and a
   * plain <a href> navigation would arrive without it and 401.
   */
  function exportPanel(dateFrom, dateTo) {
    const status = el("p", { class: "page-status-note", "aria-live": "polite" });

    const buttons = REPORT_EXPORTS.map(([key, label, description]) => {
      const button = el("button", {
        type: "button",
        class: "btn",
        text: `Download ${label.toLowerCase()}`,
        onclick: async () => {
          button.disabled = true;
          status.textContent = `Preparing the ${label.toLowerCase()} export...`;
          try {
            const blob = await downloadReport(key, dateFrom, dateTo);
            const url = URL.createObjectURL(blob);
            const link = el("a", {
              href: url,
              download: `${key}_${dateFrom || "start"}_${dateTo || "today"}.csv`,
            });
            document.body.append(link);
            link.click();
            link.remove();
            // Revoke on the next tick; revoking synchronously can beat the download.
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            status.textContent = `${label} export downloaded.`;
          } catch (error) {
            status.textContent = "";
            showToast(errorMessage(error, "Could not build that export."), { type: "error" });
          } finally {
            button.disabled = false;
          }
        },
      });
      return el("div", { class: "export-option" }, [
        button,
        el("span", { class: "export-option__hint", text: description }),
      ]);
    });

    return el("section", { class: "settings-card" }, [
      el("h2", { text: "Download" }),
      el("p", {
        class: "section-lead",
        text: "CSV files for the range above. These contain rider names and Medicaid IDs, so every download is recorded in the audit log.",
      }),
      el("div", { class: "export-grid" }, buttons),
      status,
    ]);
  }

  async function load() {
    const dateFrom = qs("#date_from").value || undefined;
    const dateTo = qs("#date_to").value || undefined;
    showLoading(content, "Loading KPIs...");
    try {
      const [summary, revenue, drivers] = await Promise.all([
        getKpiSummary(dateFrom, dateTo),
        getRevenueByMonth(dateFrom, dateTo),
        getDriverPerformance(dateFrom, dateTo).catch(() => []),
      ]);
      clear(content);

      const tile = (label, value, { accent = false, hint = null, alert = false } = {}) =>
        el(
          "div",
          {
            class: `kpi-tile${accent ? " kpi-tile--accent" : ""}${alert ? " kpi-tile--alert" : ""}`,
          },
          [
            el("div", { class: "kpi-tile__label", text: label }),
            el("div", { class: "kpi-tile__value", text: value }),
            hint ? el("div", { class: "kpi-tile__hint", text: hint }) : null,
          ]
        );

      const percent = (rate) => (rate === null ? "—" : `${(rate * 100).toFixed(1)}%`);
      const today = summary.today;
      const drivers = summary.drivers;
      const onTime = summary.on_time;

      // Right now, above the trailing-window figures: a dispatcher opening this
      // screen is asking "what is happening today", not "how was last month".
      content.append(
        el("h2", { class: "kpi-heading", text: "Right now" }),
        el("div", { class: "kpi-grid" }, [
          tile("Trips today", String(today.trips_today), { accent: true }),
          tile("In progress", String(today.active), { hint: "Assigned through picked up" }),
          tile("Awaiting confirmation", String(today.pending), {
            alert: today.pending > 0,
            hint: "Requested, not yet confirmed",
          }),
          tile("Unassigned today", String(today.unassigned), {
            alert: today.unassigned > 0,
            hint: "Confirmed with no driver",
          }),
          tile("Not yet accepted", String(today.awaiting_acceptance), {
            alert: today.awaiting_acceptance > 0,
            hint: "Assigned, driver hasn't taken it",
          }),
          tile("Will-call waiting", String(today.will_call_waiting), {
            alert: today.will_call_waiting > 0,
            hint: "Riders asking to be collected",
          }),
          tile("Drivers on duty", `${drivers.on_duty_now} / ${drivers.approved_drivers}`),
          tile("Awaiting approval", String(drivers.awaiting_approval), {
            alert: drivers.awaiting_approval > 0,
            hint: "Driver applications to review",
          }),
        ]),
        el("h2", { class: "kpi-heading", text: "Over the selected range" }),
        el("div", { class: "kpi-grid" }, [
          tile("Trips", String(summary.trip_volume.total), { accent: true }),
          tile("On-time pickups", percent(onTime.on_time_rate), {
            hint:
              onTime.total === 0
                ? "No completed pickups yet"
                : `${onTime.on_time} of ${onTime.total} within 15 min`,
          }),
          tile("Cancellation rate", percent(summary.cancellation_no_show.cancellation_rate)),
          tile("No-show rate", percent(summary.cancellation_no_show.no_show_rate)),
          tile(
            "Avg cycle time",
            summary.cycle_time.avg_cycle_minutes === null
              ? "—"
              : `${Math.round(summary.cycle_time.avg_cycle_minutes)} min`
          ),
          tile("Drivers who drove", String(drivers.drivers_with_trips)),
          tile("Billed", formatCurrency(summary.revenue.billed_total)),
          tile("Outstanding", formatCurrency(summary.revenue.outstanding_total)),
          tile("Paid", formatCurrency(summary.revenue.paid_total)),
        ])
      );

      content.append(el("h2", { text: "Revenue by month" }));
      if (revenue.length === 0) {
        showEmpty(content, "No billed revenue in range.");
      } else {
        const max = Math.max(...revenue.map((r) => Number(r.total)));
        const rows = revenue.map((entry) => {
          const pct = max > 0 ? (Number(entry.total) / max) * 100 : 0;
          return el("li", { class: "revenue-bars__row" }, [
            el("span", { text: formatMonthLabel(entry.month) }),
            el("div", { class: "revenue-bars__track" }, [el("div", { class: "revenue-bars__fill", style: `width:${pct}%` })]),
            el("span", { text: formatCurrency(entry.total) }),
          ]);
        });
        content.append(el("ul", { class: "revenue-bars" }, rows));
      }

      content.append(el("h2", { class: "kpi-heading", text: "Driver performance" }));
      if (drivers.length === 0) {
        showEmpty(content, "No driver activity in range.");
      } else {
        content.append(
          dataTable(
            ["Driver", "Van", "Trips", "Completed", "No-shows", "Miles", "Rating"],
            drivers.map((row) => [
              row.name,
              row.vehicle_plate || "—",
              String(row.trips),
              String(row.completed),
              String(row.no_shows),
              row.miles.toFixed(1),
              row.average_rating === null ? "—" : row.average_rating.toFixed(2),
            ])
          )
        );
      }

      content.append(exportPanel(dateFrom, dateTo));
    } catch {
      showError(content, "Could not load the KPI dashboard.");
    }
  }

  qs("#filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    load();
  });

  load();
}
