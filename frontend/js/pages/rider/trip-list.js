import { requireRole } from "../../api/auth.js";
import { listTrips, getTrip, cancelTrip, canCancel, CANCELLABLE_STATUSES } from "../../api/trips.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { renderHero, greetingTitle } from "../../ui/hero.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { showToast } from "../../ui/toast.js";
import {
  ACTIVE_TRIP_STATUSES,
  actionRow,
  statCards,
  nextRideCard,
  recentDestinations,
  locationCards,
  tripsTable,
} from "../../ui/dashboard.js";

const DETAIL_BASE = "/rider/trip-detail.html";

const user = await requireRole(["RIDER"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Patient Portal",
    title: greetingTitle(user),
    lead: "Book transport to your next medical appointment. Dispatch confirms every request within two hours.",
  });

  const content = qs("#content");
  let page = 1;
  // Summary (counts, next ride, past destinations) is fetched once; the table paginates.
  let summary = null;

  async function loadSummary() {
    const [upcoming, completed] = await Promise.all([
      listTrips(1, ACTIVE_TRIP_STATUSES.join(",")),
      listTrips(1, "COMPLETED"),
    ]);
    // The soonest active trip is re-fetched by id: driver rating/plate/vehicle live
    // on the detail serializer only.
    let next = upcoming.results[0] || null;
    if (next) {
      try {
        next = await getTrip(next.id);
      } catch {
        /* fall back to the list payload — the card degrades to "driver to follow" */
      }
    }
    summary = {
      upcoming: upcoming.count,
      completed: completed.count,
      next,
      destinations: recentDestinations(completed.results),
    };
  }

  function renderNextRide(trip) {
    const cancellable = canCancel(trip);
    return nextRideCard(trip, {
      detailBase: DETAIL_BASE,
      cancel: {
        enabled: cancellable,
        note: CANCELLABLE_STATUSES.includes(trip.status)
          ? "This ride is within 24 hours of pickup — call dispatch to change it."
          : null,
        onCancel: async (event) => {
          const btn = event.currentTarget;
          btn.disabled = true;
          try {
            await cancelTrip(trip.id);
            showToast("Ride cancelled.", { type: "success" });
            summary = null;
            page = 1;
            load();
          } catch {
            btn.disabled = false;
            showToast("Could not cancel this ride.", { type: "error" });
          }
        },
      },
    });
  }

  async function load() {
    showLoading(content, "Loading your trips...");
    try {
      if (!summary) await loadSummary();
      const data = await listTrips(page);
      clear(content);

      content.append(
        actionRow([
          { label: "Book a ride", href: "/rider/book.html", primary: true },
          { label: "Your invoices", href: "/rider/invoices.html" },
        ])
      );

      content.append(
        statCards([
          { label: "Upcoming", value: summary.upcoming, accent: true },
          { label: "Completed", value: summary.completed },
          { label: "Total trips", value: data.count },
        ])
      );

      if (summary.next) {
        content.append(renderNextRide(summary.next));
      }

      if (summary.destinations.length > 0) {
        content.append(
          el("h2", { text: "Book again" }),
          el("p", {
            class: "section-lead",
            text: "Destinations you've travelled to before — one tap to start a new booking.",
          }),
          locationCards(summary.destinations)
        );
      }

      content.append(el("h2", { text: "Upcoming & past trips" }));
      if (data.results.length === 0) {
        showEmpty(content, "No trips yet.", { label: "Book your first ride", href: "/rider/book.html" });
      } else {
        content.append(tripsTable(data.results, DETAIL_BASE));
        content.append(
          el("p", { class: "section-lead" }, [
            "Fares and receipts live in ",
            el("a", { href: "/rider/invoices.html", text: "your invoices" }),
            ".",
          ])
        );
      }

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
      showError(content, "Could not load trips.");
    }
  }

  load();
}
