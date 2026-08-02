import { el } from "./dom.js";

// Read-only star display for a numeric rating (0–5). Returns a span.
export function ratingStars(value, { showNumber = true } = {}) {
  const rounded = Math.max(0, Math.min(5, Math.round(Number(value) || 0)));
  const glyphs = "★".repeat(rounded) + "☆".repeat(5 - rounded);
  const children = [el("span", { class: "rating-stars__glyphs", text: glyphs })];
  if (showNumber && value != null) {
    children.push(el("span", { class: "rating-stars__num", text: Number(value).toFixed(1) }));
  }
  return el("span", { class: "rating-stars" }, children);
}

// Compact "4.8 (12)" style summary for a driver's average rating.
export function ratingSummary(average, count) {
  if (average == null || !count) {
    return el("span", { class: "rating-stars__num", text: "No ratings yet" });
  }
  return el("span", { class: "rating-stars" }, [
    el("span", { class: "rating-stars__glyphs", text: "★" }),
    el("span", { class: "rating-stars__num", text: `${Number(average).toFixed(1)} · ${count} rating${count === 1 ? "" : "s"}` }),
  ]);
}
