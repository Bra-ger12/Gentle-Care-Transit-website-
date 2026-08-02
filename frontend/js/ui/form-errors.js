import { clearFieldError, setFieldError } from "./validation.js";

/**
 * Turning a DRF error response into something a person can act on.
 *
 * The server already knows exactly what went wrong -- "that address is outside
 * the area we serve", "you must wait 10 minutes before filing a no-show". Every
 * form used to discard that and print one generic sentence, which left riders
 * re-typing a correct address because the real problem was somewhere else
 * entirely. These helpers put the server's own words on the screen, against the
 * field they belong to wherever the server named one.
 */

// DRF's key for errors that belong to the whole payload rather than one field.
const NON_FIELD = "non_field_errors";

const FALLBACK = "Something went wrong. Please try again.";

/** Flatten whatever DRF put in this key into one readable sentence. */
function messageFrom(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(messageFrom).filter(Boolean).join(" ");
  if (typeof value === "object") {
    return Object.values(value).map(messageFrom).filter(Boolean).join(" ");
  }
  return String(value);
}

/**
 * The best single sentence describing this failure.
 *
 * Prefers a `detail` (DRF's own phrasing for permission and throttle errors),
 * then non-field errors, then the first field error — with the field named, so
 * "Pickup and drop-off cannot be the same address" doesn't arrive contextless.
 */
export function errorMessage(error, fallback = FALLBACK) {
  const data = error?.data;

  if (error?.status === 401) return "Your session has expired. Please sign in again.";
  if (error?.status === 403) return "You don't have permission to do that.";
  if (error?.status >= 500) return "The server had a problem. Please try again in a moment.";
  if (data == null) return error?.status === 0 ? "No connection to the server." : fallback;

  if (typeof data === "string") return data || fallback;
  if (Array.isArray(data)) return messageFrom(data) || fallback;

  if (data.detail) return messageFrom(data.detail);
  if (data[NON_FIELD]) return messageFrom(data[NON_FIELD]);

  const [field, value] = Object.entries(data)[0] || [];
  if (!field) return fallback;
  return messageFrom(value) || fallback;
}

/** Human label for a field name, for messages that name one. */
export function fieldLabel(name) {
  return name
    .replace(/_/g, " ")
    .replace(/\bid\b/i, "")
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
}

/**
 * Paint per-field errors onto the inputs they belong to.
 *
 * `fields` maps the server's field names to the actual input elements. Anything
 * the server complained about that isn't in the map is returned as leftover
 * text for the form-level banner, so no message is ever silently dropped.
 */
export function applyFieldErrors(error, fields = {}) {
  for (const input of Object.values(fields)) {
    if (input) clearFieldError(input);
  }

  const data = error?.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return errorMessage(error);
  }

  const leftovers = [];
  let painted = 0;

  for (const [name, value] of Object.entries(data)) {
    const message = messageFrom(value);
    if (!message) continue;

    const input = fields[name];
    if (input) {
      setFieldError(input, message);
      painted += 1;
      if (painted === 1) input.focus({ preventScroll: false });
    } else if (name === NON_FIELD || name === "detail") {
      leftovers.push(message);
    } else {
      leftovers.push(`${fieldLabel(name)}: ${message}`);
    }
  }

  if (leftovers.length) return leftovers.join(" ");
  return painted ? "" : errorMessage(error);
}

/**
 * Show a form-level failure in a banner element, returning whether anything
 * was shown. Pass the same `fields` map to also mark the inputs.
 */
export function showFormError(banner, error, fields = {}) {
  const message = applyFieldErrors(error, fields);
  if (!banner) return Boolean(message);

  if (message) {
    banner.textContent = message;
    banner.hidden = false;
  } else {
    banner.textContent = "";
    banner.hidden = true;
  }
  return Boolean(message);
}

/** Clear a banner and any field markers before a fresh submit. */
export function clearFormErrors(banner, fields = {}) {
  if (banner) {
    banner.textContent = "";
    banner.hidden = true;
  }
  for (const input of Object.values(fields)) {
    if (input) clearFieldError(input);
  }
}
