import { el } from "./dom.js";

// Time-of-day greeting for dashboard heroes (client local time).
export function timeGreeting(date = new Date()) {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

// "Good evening, Vera." — or just "Good evening." when the user has no first name.
export function greetingTitle(user, date = new Date()) {
  const name = ((user && user.first_name) || "").trim();
  return name ? `${timeGreeting(date)}, ${name}.` : `${timeGreeting(date)}.`;
}

// Renders the gradient greeting header used at the top of each role dashboard.
// `lead` may be a string or a DOM node (e.g. to include <strong> emphasis); omit for none.
export function renderHero(container, { eyebrow, title, lead }) {
  if (!container) return;
  container.className = "dashboard-hero";
  const children = [
    el("p", { class: "dashboard-hero__eyebrow", text: eyebrow }),
    el("h1", { class: "dashboard-hero__title", text: title }),
  ];
  if (lead != null) {
    children.push(
      lead instanceof Node
        ? lead
        : el("p", { class: "dashboard-hero__lead", text: lead })
    );
  }
  container.replaceChildren(...children);
}
