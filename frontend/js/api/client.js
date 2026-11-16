// Django serves this site itself in dev, so the API normally lives on the page's own
// origin — same-origin means no CORS preflight and no cross-port refresh cookie. The
// exception is running the frontend from a standalone static server (the documented
// `python -m http.server 5173`), which has to reach across to the backend.
const STANDALONE_STATIC_PORTS = new Set(["5173", "3000", "8080"]);

export const API_BASE = STANDALONE_STATIC_PORTS.has(window.location.port)
  ? "http://localhost:8000/api"
  : `${window.location.origin}/api`;

let accessToken = null;
let unauthorizedHandler = null;
let csrfToken = null;

// FIX #6: Django validates unsafe cookie-backed requests with this CSRF token.
export function getCsrfToken() {
  return csrfToken || document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

export function setCsrfToken(token) {
  csrfToken = token || null;
}

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

async function doFetch(path, { method = "GET", body, isForm = false, auth = true } = {}) {
  const headers = {};
  if (!isForm && body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const unsafe = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method.toUpperCase());
  const token = getCsrfToken();
  if (unsafe && token) headers["X-CSRFToken"] = decodeURIComponent(token);

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",
    headers,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  return response;
}

export async function apiFetch(path, options = {}, _retried = false) {
  const response = await doFetch(path, options);

  if (response.status === 401 && options.auth !== false && !_retried && unauthorizedHandler) {
    const refreshed = await unauthorizedHandler();
    if (refreshed) {
      return apiFetch(path, options, true);
    }
  }

  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch {
      // no JSON body
    }
    const error = new Error(`Request to ${path} failed with ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  if (response.status === 204 || response.status === 205) return null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response;
}

export async function apiFetchBlob(path, options = {}) {
  const response = await doFetch(path, options);
  if (!response.ok) {
    const error = new Error(`Request to ${path} failed with ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.blob();
}
