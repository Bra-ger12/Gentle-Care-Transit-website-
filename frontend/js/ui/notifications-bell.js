import { el } from "./dom.js";
import { formatDateTime } from "./format.js";
import { showToast } from "./toast.js";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/notifications.js";
import { openSocket } from "../api/realtime.js";

const BELL_SVG =
  '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>';

const TRIP_DETAIL_PATH = {
  RIDER: "/rider/trip-detail.html",
  DRIVER: "/driver/trip-detail.html",
  ADMIN: "/admin/index.html",
};

// Pages that want to react to live notifications (e.g. the driver board refreshing
// its manifest when dispatch assigns a trip) subscribe here rather than opening a
// second `notifications/` socket alongside the bell's.
const subscribers = new Set();

/** Listen to notifications as they arrive. Returns an unsubscribe function. */
export function onNotification(handler) {
  subscribers.add(handler);
  return () => subscribers.delete(handler);
}

function notificationHref(notification, role) {
  if (!notification.related_trip) return null;
  const base = TRIP_DETAIL_PATH[role];
  if (!base) return null;
  if (role === "ADMIN") return base; // no per-trip admin page — go to dispatch
  return `${base}?id=${notification.related_trip}`;
}

export function mountNotificationBell(container, user) {
  let items = [];
  let unread = 0;
  let open = false;

  const badge = el("span", { class: "notif__badge", hidden: "hidden" });
  const button = el("button", {
    class: "notif__btn",
    type: "button",
    "aria-label": "Notifications",
    html: BELL_SVG,
  });
  button.append(badge);

  const list = el("div", { class: "notif__list" });
  const markAllBtn = el("button", {
    class: "notif__mark-all",
    type: "button",
    text: "Mark all read",
    onclick: async (e) => {
      e.stopPropagation();
      try {
        await markAllNotificationsRead();
      } catch {
        // ignore — UI still updates optimistically
      }
      items = items.map((n) => ({ ...n, is_read: true }));
      setUnread(0);
      renderList();
    },
  });
  const panel = el("div", { class: "notif__panel", hidden: "hidden" }, [
    el("div", { class: "notif__panel-head" }, [
      el("span", { text: "Notifications" }),
      markAllBtn,
    ]),
    list,
  ]);

  const wrap = el("div", { class: "notif" }, [button, panel]);
  container.prepend(wrap);

  function setUnread(count) {
    unread = Math.max(0, count);
    badge.textContent = unread > 99 ? "99+" : String(unread);
    badge.hidden = unread === 0;
  }

  function renderList() {
    list.replaceChildren();
    if (items.length === 0) {
      list.append(el("p", { class: "notif__empty", text: "No notifications yet." }));
      return;
    }
    for (const n of items.slice(0, 15)) {
      const href = notificationHref(n, user.role);
      const item = el(
        "button",
        {
          type: "button",
          class: `notif__item${n.is_read ? "" : " notif__item--unread"}`,
          onclick: async () => {
            if (!n.is_read) {
              n.is_read = true;
              setUnread(unread - 1);
              renderList();
              try {
                await markNotificationRead(n.id);
              } catch {
                // ignore
              }
            }
            if (href) window.location.href = href;
          },
        },
        [
          el("span", { class: "notif__item-title", text: n.title }),
          el("span", { class: "notif__item-body", text: n.body }),
          el("span", { class: "notif__item-time", text: formatDateTime(n.created_at) }),
        ]
      );
      list.append(item);
    }
  }

  function togglePanel(next) {
    open = next === undefined ? !open : next;
    panel.hidden = !open;
    wrap.classList.toggle("notif--open", open);
  }

  button.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePanel();
  });
  panel.addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", () => togglePanel(false));

  // Initial load.
  listNotifications()
    .then((data) => {
      items = data.results || [];
      setUnread(items.filter((n) => !n.is_read).length);
      renderList();
    })
    .catch(() => {
      renderList();
    });

  // Live updates.
  const socket = openSocket("notifications/", {
    onJson: (msg) => {
      if (msg.event === "unread_count") {
        setUnread(msg.unread_count);
      } else if (msg.event === "notification") {
        items = [msg.notification, ...items];
        setUnread(msg.unread_count ?? unread + 1);
        renderList();
        showToast(msg.notification.title, { type: "info" });
        for (const handler of subscribers) {
          try {
            handler(msg.notification);
          } catch {
            // a subscriber must never break the bell
          }
        }
      }
    },
  });

  window.addEventListener("beforeunload", () => socket.close());
  return { close: () => socket.close() };
}
