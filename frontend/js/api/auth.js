import { API_BASE, apiFetch, setAccessToken, getAccessToken, setUnauthorizedHandler } from "./client.js";

let cachedUser = null;
let refreshPromise = null;

export function currentUser() {
  return cachedUser;
}

export async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh/`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const data = await response.json();
        setAccessToken(data.access);
        return data.access;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

setUnauthorizedHandler(async () => {
  const token = await refreshAccessToken();
  return Boolean(token);
});

export async function getCurrentUser() {
  const user = await apiFetch("/auth/me/");
  cachedUser = user;
  return user;
}

/** Update the signed-in user's own name / email / phone. */
export async function updateCurrentUser(payload) {
  const user = await apiFetch("/auth/me/", { method: "PATCH", body: payload });
  cachedUser = user;
  return user;
}

export async function bootSession() {
  try {
    const token = await refreshAccessToken();
    if (!token) {
      cachedUser = null;
      return null;
    }
    return await getCurrentUser();
  } catch {
    cachedUser = null;
    return null;
  }
}

export async function login(identifier, password) {
  const data = await apiFetch("/auth/login/", { method: "POST", body: { identifier, password }, auth: false });
  setAccessToken(data.access);
  return getCurrentUser();
}

export async function register(payload) {
  return apiFetch("/auth/register/", { method: "POST", body: payload, auth: false });
}

/** Confirm an address from the emailed link. Unauthenticated: the link is
 * usually opened in a different browser from the one that registered. */
export function confirmEmail(uid, token) {
  return apiFetch("/auth/verify-email/confirm/", {
    method: "POST",
    body: { uid, token },
    auth: false,
  });
}

export function resendVerificationEmail() {
  return apiFetch("/auth/verify-email/resend/", { method: "POST" });
}

export async function logout() {
  try {
    await apiFetch("/auth/logout/", { method: "POST" });
  } catch {
    // ignore — clear local session regardless
  } finally {
    setAccessToken(null);
    cachedUser = null;
  }
}

export const ROLE_HOME = {
  RIDER: "/rider/index.html",
  DRIVER: "/driver/index.html",
  ADMIN: "/admin/index.html",
};

export async function requireRole(allowedRoles) {
  const user = await bootSession();
  if (!user) {
    window.location.replace("/login.html");
    return null;
  }
  if (!allowedRoles.includes(user.role)) {
    window.location.replace("/forbidden.html");
    return null;
  }
  return user;
}

export { getAccessToken };
