import { el, clear } from "./dom.js";
import { logout, ROLE_HOME } from "../api/auth.js";
import { mountNotificationBell } from "./notifications-bell.js";

// The supplied brand mark, extracted from assets/LOGO.png: the house-and-hand
// icon without the wordmark, because the brand block already renders the name as
// live text beside it. Referenced rather than inlined so replacing the file
// propagates everywhere without touching markup.
const LOGO_SRC = "/assets/logo-mark.png";

// 20x20 stroked glyphs, one per nav destination (sidebar only).
const ICONS = {
  trips: '<path d="M3 13h14M5 13V8l2-4h6l2 4v5M6 16v1M14 16v1M6.5 10.5h7"/>',
  book: '<path d="M10 4v12M4 10h12"/>',
  invoices: '<path d="M5 3h10v14l-2.5-1.5L10 17l-2.5-1.5L5 17V3zM8 7h4M8 10h4"/>',
  dispatch: '<path d="M10 3v14M3 10h14M10 3a7 7 0 010 14 7 7 0 010-14z"/>',
  drivers: '<path d="M10 10a3 3 0 100-6 3 3 0 000 6zM4 17a6 6 0 0112 0"/>',
  accounts: '<path d="M7 9a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM2.5 16a4.5 4.5 0 019 0M13 6.5a2.5 2.5 0 010 5M14.5 16a4.5 4.5 0 00-1.5-3.4"/>',
  vehicles: '<path d="M3 12h14M4.5 12V8l1.5-3h8l1.5 3v4M6 15v1M14 15v1M3 12v3h14v-3"/>',
  rates: '<path d="M10 3v14M13 6.5c0-1.4-1.3-2.5-3-2.5S7 5.1 7 6.5 8.3 9 10 9s3 1.1 3 2.5-1.3 2.5-3 2.5-3-1.1-3-2.5"/>',
  export: '<path d="M10 3v9M6.5 8.5L10 12l3.5-3.5M4 15h12"/>',
  reports: '<path d="M4 16V9M8 16V5M12 16v-4M16 16v-8"/>',
  recurring: '<path d="M4 8a6 6 0 019.5-4.9M16 12a6 6 0 01-9.5 4.9M4 4v4h4M16 16v-4h-4"/>',
  schedule: '<path d="M4 5h12v11H4zM4 8h12M7 3v3M13 3v3M7 11h2M11 11h2"/>',
  pay: '<path d="M2.5 5.5h15v9h-15zM10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5M5 8v4M15 8v4"/>',
  inspect: '<path d="M9 3.5l5.5 2v4c0 3-2.2 5.5-5.5 6.5-3.3-1-5.5-3.5-5.5-6.5v-4L9 3.5zM7 9l1.6 1.6L11.5 7.5"/>',
  account: '<path d="M10 10a3 3 0 100-6 3 3 0 000 6zM4 17a6 6 0 0112 0"/>',
  settings:
    '<path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5"/><path d="M15.6 12a1.4 1.4 0 00.3 1.5l.1.1a1.6 1.6 0 11-2.3 2.3l-.1-.1a1.4 1.4 0 00-2.4 1v.2a1.6 1.6 0 11-3.2 0v-.1a1.4 1.4 0 00-2.4-1l-.1.1a1.6 1.6 0 11-2.3-2.3l.1-.1a1.4 1.4 0 00-1-2.4H2.2a1.6 1.6 0 110-3.2h.1a1.4 1.4 0 001-2.4l-.1-.1a1.6 1.6 0 112.3-2.3l.1.1a1.4 1.4 0 002.4-1V2.2a1.6 1.6 0 113.2 0v.1a1.4 1.4 0 002.4 1l.1-.1a1.6 1.6 0 112.3 2.3l-.1.1a1.4 1.4 0 001 2.4h.2a1.6 1.6 0 110 3.2h-.1a1.4 1.4 0 00-1.3.8z"/>',
};

const icon = (key) =>
  el("span", {
    class: "app-nav__icon",
    html: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${ICONS[key] || ""}</svg>`,
  });

const LINKS_BY_ROLE = {
  RIDER: [
    ["/rider/index.html", "Your trips", "trips"],
    ["/rider/book.html", "Book a trip", "book"],
    ["/rider/recurring.html", "Recurring rides", "recurring"],
    ["/rider/invoices.html", "Invoices", "invoices"],
    ["/account.html", "Account", "account"],
  ],
  DRIVER: [
    ["/driver/index.html", "Today", "trips"],
    ["/driver/schedule.html", "Schedule", "schedule"],
    ["/driver/availability.html", "Availability", "recurring"],
    ["/driver/vehicle-check.html", "Vehicle check", "inspect"],
    ["/driver/reports.html", "Reports", "reports"],
    ["/account.html", "Account", "account"],
  ],
  ADMIN: [
    ["/admin/index.html", "Dispatch", "dispatch"],
    ["/admin/book.html", "Phone booking", "book"],
    ["/admin/drivers.html", "Drivers", "drivers"],
    ["/admin/accounts.html", "Accounts", "accounts"],
    ["/admin/vehicles.html", "Vehicles", "vehicles"],
    ["/admin/inspections.html", "Inspections", "inspect"],
    ["/admin/invoices.html", "Invoices", "invoices"],
    ["/admin/payroll.html", "Driver pay", "pay"],
    ["/admin/rate-schedules.html", "Rate schedules", "rates"],
    ["/admin/medicaid-export.html", "Medicaid export", "export"],
    ["/admin/reports.html", "Reports", "reports"],
    ["/admin/settings.html", "Settings", "settings"],
    ["/account.html", "Account", "account"],
  ],
};

const ROLE_LABEL = { RIDER: "Patient Portal", DRIVER: "Driver Portal", ADMIN: "Administrator Portal" };

// Roles whose shell is a left sidebar; the driver portal keeps the top bar so its
// operations view can use the full width for the manifest / active-trip columns.
const SIDEBAR_ROLES = new Set(["RIDER", "ADMIN"]);

function isCurrent(href) {
  const path = window.location.pathname;
  return path === href || (href.endsWith("/index.html") && path === href.slice(0, -"index.html".length));
}

export function renderNav(container, user) {
  clear(container);
  const sidebar = SIDEBAR_ROLES.has(user.role);
  container.className = sidebar ? "app-nav app-nav--side" : "app-nav";
  document.body.classList.toggle("has-sidebar", sidebar);

  const brand = el("a", { class: "brand", href: ROLE_HOME[user.role] || "/" }, [
    el("span", { class: "logo-mark" }, [
      el("img", { src: LOGO_SRC, alt: "", width: "20", height: "20" }),
    ]),
    el("span", { class: "brand__text" }, [
      el("span", { class: "brand__name", text: "Gentle Care Transit" }),
      el("span", { class: "brand__subtitle", text: ROLE_LABEL[user.role] || "" }),
    ]),
  ]);

  const links = (LINKS_BY_ROLE[user.role] || []).map(([href, label, iconKey]) => {
    const current = isCurrent(href);
    const attrs = { href, class: current ? "is-current" : "" };
    if (current) attrs["aria-current"] = "page";
    return el("a", attrs, sidebar ? [icon(iconKey), el("span", { text: label })] : [label]);
  });

  const logoutBtn = el("button", {
    class: "btn",
    text: "Log out",
    onclick: async () => {
      await logout();
      window.location.replace("/login.html");
    },
  });

  const userSection = el("div", { class: "app-nav__user" }, [
    el("span", { class: "app-nav__name", text: `${user.first_name} ${user.last_name}` }),
    logoutBtn,
  ]);

  container.append(brand, el("div", { class: "app-nav__links" }, links), userSection);

  // Live notification bell, inserted before the user's name.
  mountNotificationBell(userSection, user);

  if (!document.querySelector(".app-footer")) {
    document.body.append(
      el("footer", { class: "app-footer" }, [
        el("span", { text: "© 2026 Gentle Care Transit · Bismarck, ND · Licensed NEMT Provider" }),
        el("div", { class: "app-footer__links" }, [
          el("a", { href: "/privacy.html", text: "Privacy" }),
          el("a", { href: "/terms.html", text: "Terms" }),
          el("a", { href: "/contact.html", text: "Contact" }),
        ]),
      ])
    );
  }
}
