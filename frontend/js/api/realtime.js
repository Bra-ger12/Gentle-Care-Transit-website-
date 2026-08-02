import { API_BASE, getAccessToken } from "./client.js";
import { refreshAccessToken } from "./auth.js";

function wsBase() {
  const url = new URL(API_BASE);
  const proto = url.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${url.host}`;
}

/**
 * Open a resilient WebSocket to `ws/<path>` on the backend.
 *
 * The access token is passed in the query string (browsers can't set an
 * Authorization header on a WebSocket). We refresh it before each connect so a
 * reconnect after the 15-minute access-token lifetime still authenticates.
 * Auto-reconnects with capped exponential backoff until `.close()` is called.
 *
 * Returns `{ send(obj), close() }`.
 */
export function openSocket(path, { onJson, onOpen, onClose } = {}) {
  let ws = null;
  let closed = false;
  let attempt = 0;

  async function connect() {
    if (closed) return;
    const token = (await refreshAccessToken()) || getAccessToken();
    if (closed) return;

    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    ws = new WebSocket(`${wsBase()}/ws/${path}${query}`);

    ws.onopen = () => {
      attempt = 0;
      if (onOpen) onOpen();
    };
    ws.onmessage = (event) => {
      if (!onJson) return;
      try {
        onJson(JSON.parse(event.data));
      } catch {
        // ignore malformed frames
      }
    };
    ws.onclose = () => {
      if (onClose) onClose();
      if (closed) return;
      attempt += 1;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
      setTimeout(connect, delay);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        // no-op
      }
    };
  }

  connect();

  return {
    send(obj) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    },
    close() {
      closed = true;
      if (ws) {
        try {
          ws.close();
        } catch {
          // no-op
        }
      }
    },
  };
}
