import { requireRole } from "../../api/auth.js";
import { listRecurringSeries, deactivateRecurringSeries } from "../../api/trips.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { renderHero } from "../../ui/hero.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { routeLeg, actionRow } from "../../ui/dashboard.js";
import { WEEKDAYS, MOBILITY_LABELS, formatDate } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const WEEKDAY_LABELS = Object.fromEntries(WEEKDAYS.map((d) => [d.value, d.label]));

/** "Mon · Wed · Fri" in week order, whatever order the API returns them in. */
function weekdayList(weekdays) {
  return WEEKDAYS.filter((d) => (weekdays || []).includes(d.value))
    .map((d) => d.label)
    .join(" · ");
}

/** "9:00 AM" from the API's "09:00:00". */
function prettyTime(value) {
  if (!value) return "—";
  const [hours, minutes] = value.split(":");
  const date = new Date();
  date.setHours(Number(hours), Number(minutes), 0, 0);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

const user = await requireRole(["RIDER"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Patient Portal",
    title: "Recurring rides",
    lead: "Standing appointments book themselves ahead of time. Ending a series leaves any rides already booked in place — cancel those from your trips list.",
  });

  const content = qs("#content");
  let page = 1;

  function seriesCard(series, onChanged) {
    const active = series.is_active;
    const card = el("article", { class: `series-card${active ? "" : " series-card--ended"}` }, [
      el("div", { class: "series-card__head" }, [
        el("span", { class: "series-card__days", text: weekdayList(series.weekdays) || "No days set" }),
        el("span", {
          class: `chip ${active ? "series-card__badge" : "series-card__badge series-card__badge--off"}`,
          text: active ? "Active" : "Ended",
        }),
      ]),
      el("p", { class: "series-card__time" }, [
        el("strong", { text: prettyTime(series.pickup_time) }),
        el("span", {
          class: "series-card__window",
          text: series.end_date
            ? ` · ${formatDate(series.start_date)} to ${formatDate(series.end_date)}`
            : ` · from ${formatDate(series.start_date)}, no end date`,
        }),
      ]),
      el("div", { class: "series-card__route" }, [
        routeLeg("pickup", "Pickup", series.pickup_address),
        routeLeg("dropoff", "Destination", series.dropoff_address),
      ]),
    ]);

    if (series.mobility_need) {
      card.append(
        el("p", {}, [
          el("span", {
            class: "chip",
            text: MOBILITY_LABELS[series.mobility_need] || series.mobility_need,
          }),
        ])
      );
    }
    if (series.notes) card.append(el("p", { class: "series-card__notes", text: series.notes }));

    if (active) {
      const endBtn = el("button", {
        class: "btn btn--danger",
        text: "End this series",
        onclick: async () => {
          if (!window.confirm("Stop booking new rides from this series? Rides already booked stay on your schedule.")) {
            return;
          }
          endBtn.disabled = true;
          try {
            await deactivateRecurringSeries(series.id);
            showToast("Series ended — no new rides will be booked.", { type: "success" });
            onChanged();
          } catch {
            endBtn.disabled = false;
            showToast("Could not end this series.", { type: "error" });
          }
        },
      });
      card.append(el("div", { class: "series-card__actions" }, [endBtn]));
    }

    return card;
  }

  async function load() {
    showLoading(content, "Loading your recurring rides...");
    try {
      const data = await listRecurringSeries(page);
      clear(content);

      content.append(
        actionRow([
          { label: "Set up a recurring ride", href: "/rider/book.html", primary: true },
          { label: "Your trips", href: "/rider/index.html" },
        ])
      );

      if (data.results.length === 0) {
        showEmpty(content, "No recurring rides yet.", {
          label: "Book a repeating ride",
          href: "/rider/book.html",
        });
        return;
      }

      data.results.forEach((series) => content.append(seriesCard(series, load)));

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
      showError(content, "Could not load your recurring rides.");
    }
  }

  load();
}
