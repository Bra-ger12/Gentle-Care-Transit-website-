import { requireApprovedDriver } from "../../api/drivers.js";
import { getDriverReport } from "../../api/reports.js";
import { getEarningsSummary, listEarnings } from "../../api/payroll.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { showLoading, showError } from "../../ui/status.js";
import { ratingSummary } from "../../ui/rating.js";
import { formatCurrency, formatDate } from "../../ui/format.js";

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  const tile = (label, value, accent) =>
    el("div", { class: accent ? "kpi-tile kpi-tile--accent" : "kpi-tile" }, [
      el("div", { class: "kpi-tile__label", text: label }),
      el("div", { class: "kpi-tile__value", text: value }),
    ]);

  /** Per-trip pay for the same range, so the total can be checked line by line. */
  function earningsSection(summary, earnings) {
    const section = el("section", {}, [el("h2", { text: "Earnings" })]);
    if (!summary || summary.trips === 0) {
      section.append(
        el("p", {
          class: "page-status-note",
          text: "No earnings recorded for this range. Earnings are created from completed trips once an administrator has a pay rate on file for you.",
        })
      );
      return section;
    }

    section.append(
      el("div", { class: "kpi-grid" }, [
        tile("Earned", formatCurrency(summary.total_earned), true),
        tile("Unpaid", formatCurrency(summary.unpaid_amount)),
        tile("Paid trips", String(summary.trips)),
      ])
    );

    if (earnings.length > 0) {
      const rows = earnings.map((e) =>
        el("tr", { class: "dispatch-table__row" }, [
          el("td", { text: formatDate(e.earned_on) }),
          el("td", { text: e.trip_route }),
          el("td", { class: "mono", text: Number(e.mileage_snapshot).toFixed(1) }),
          el("td", { class: "mono", text: `${formatCurrency(e.per_trip_base)} + ${formatCurrency(e.mileage_amount)}` }),
          el("td", { class: "mono", text: formatCurrency(e.total_amount) }),
          el("td", {
            text: e.is_paid ? `Paid${e.payment_reference ? ` · ${e.payment_reference}` : ""}` : "Unpaid",
          }),
        ])
      );
      section.append(dataTable(["Date", "Trip", "Miles", "Base + miles", "Total", "Status"], rows));
    }
    return section;
  }

  async function load() {
    const dateFrom = qs("#date_from").value || undefined;
    const dateTo = qs("#date_to").value || undefined;
    showLoading(content, "Loading your report...");
    try {
      const [r, summary, earnings] = await Promise.all([
        getDriverReport(dateFrom, dateTo),
        getEarningsSummary({ dateFrom, dateTo }).catch(() => null),
        listEarnings({ dateFrom, dateTo }).catch(() => ({ results: [] })),
      ]);
      clear(content);
      content.append(
        el("div", { class: "kpi-grid" }, [
          tile("Trips", String(r.total_trips), true),
          tile("Completed", String(r.completed)),
          tile("No-shows", String(r.no_shows)),
          tile("Cancelled", String(r.cancelled)),
          tile("Miles driven", Number(r.total_miles).toFixed(1)),
        ])
      );
      content.append(
        el("div", { class: "trip-detail" }, [
          el("p", { class: "kpi-tile__label", text: "Your all-time driver rating" }),
          el("p", {}, [ratingSummary(r.average_rating, r.ratings_count)]),
        ])
      );
      content.append(earningsSection(summary, earnings.results || []));
    } catch {
      showError(content, "Could not load your report.");
    }
  }

  qs("#filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    load();
  });

  load();
}
