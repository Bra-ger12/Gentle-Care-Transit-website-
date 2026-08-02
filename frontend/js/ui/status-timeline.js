import { el } from "./dom.js";

const STEPS = [
  ["ASSIGNED", "Assigned"],
  ["EN_ROUTE", "En route"],
  ["ARRIVED", "Driver arrived"],
  ["PICKED_UP", "Picked up"],
  ["COMPLETED", "Completed"],
];
const ORDER = STEPS.map(([code]) => code);

/** A four-step progress rail for the live-tracking view. Terminal off-path
 * statuses (Cancelled / No-show) highlight nothing — the status badge covers them. */
export function statusTimeline(status) {
  const idx = ORDER.indexOf(status);
  return el(
    "ol",
    { class: "track-timeline" },
    STEPS.map(([, label], i) => {
      let cls = "track-timeline__step";
      if (idx >= 0 && i < idx) cls += " is-done";
      else if (idx >= 0 && i === idx) cls += " is-current";
      return el("li", { class: cls }, [
        el("span", { class: "track-timeline__dot" }),
        el("span", { class: "track-timeline__label", text: label }),
      ]);
    })
  );
}
