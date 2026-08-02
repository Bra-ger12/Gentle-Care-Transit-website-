import { requireApprovedDriver } from "../../api/drivers.js";
import { listTrips } from "../../api/trips.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { renderHero } from "../../ui/hero.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { tripStatusBadge } from "../../ui/badges.js";
import { ratingStars } from "../../ui/rating.js";
import { MOBILITY_LABELS, formatDate, TRIP_STATUS_LABELS } from "../../ui/format.js";
import { ACTIVE_TRIP_STATUSES } from "../../ui/dashboard.js";

const DETAIL_BASE = "/driver/trip-detail.html";

// The board covers one day at a time; this page is every trip ever assigned to you.
const FILTERS = [
  ["", "All trips"],
  [ACTIVE_TRIP_STATUSES.join(","), "Still to drive"],
  ["COMPLETED", "Completed"],
  ["NO_SHOW", "No-shows"],
  ["CANCELLED", "Cancelled"],
];

const timeOnly = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Driver Portal",
    title: "Your schedule",
    lead: "Every trip dispatch has assigned you, oldest first — today's board only covers a single day.",
  });

  const content = qs("#content");
  let page = 1;
  let status = "";

  function filterBar() {
    return el(
      "div",
      { class: "filter-bar" },
      FILTERS.map(([value, label]) =>
        el("button", {
          class: `btn filter-bar__btn${status === value ? " is-current" : ""}`,
          type: "button",
          text: label,
          onclick: () => {
            status = value;
            page = 1;
            load();
          },
        })
      )
    );
  }

  function scheduleTable(trips) {
    const rows = trips.map((trip) =>
      el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: formatDate(trip.scheduled_pickup_time) }),
        el("td", { class: "mono", text: timeOnly(trip.scheduled_pickup_time) }),
        el("td", {}, [
          el("a", { href: `${DETAIL_BASE}?id=${trip.id}`, text: trip.dropoff_address }),
          el("div", { class: "ops-row__muted", text: `from ${trip.pickup_address}` }),
        ]),
        el("td", {
          text: trip.mobility_need ? MOBILITY_LABELS[trip.mobility_need] || trip.mobility_need : "—",
        }),
        el("td", { class: "mono", text: trip.mileage ? Number(trip.mileage).toFixed(1) : "—" }),
        el("td", {}, [tripStatusBadge(trip.status)]),
        el("td", {}, [trip.rating ? ratingStars(trip.rating) : el("span", { class: "ops-row__muted", text: "—" })]),
      ])
    );
    return dataTable(["Date", "Time", "Route", "Needs", "Miles", "Status", "Rating"], rows);
  }

  async function load() {
    showLoading(content, "Loading your schedule...");
    try {
      const data = await listTrips(page, status || undefined);
      clear(content);
      content.append(filterBar());

      if (data.results.length === 0) {
        showEmpty(
          content,
          status
            ? `No ${(TRIP_STATUS_LABELS[status] || "matching").toLowerCase()} trips.`
            : "No trips assigned to you yet."
        );
        return;
      }

      content.append(
        el("p", { class: "section-lead", text: `${data.count} trip${data.count === 1 ? "" : "s"} assigned to you.` }),
        scheduleTable(data.results)
      );

      const paginationEl = el("div", { id: "pagination" });
      content.append(paginationEl);
      renderPagination(
        paginationEl,
        data,
        () => {
          page -= 1;
          load();
        },
        () => {
          page += 1;
          load();
        }
      );
    } catch {
      showError(content, "Could not load your schedule.");
    }
  }

  load();
}
