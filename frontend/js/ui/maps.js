import { apiFetch } from "../api/client.js";

let loadPromise = null;

/**
 * Load the Google Maps JS API once, using the browser key served by the backend
 * (`/api/public-config/`) so no key is hard-coded in the static site. Resolves to
 * `window.google.maps`. Rejects if no key is configured or the script fails.
 */
export function loadGoogleMaps() {
  if (window.google && window.google.maps) return Promise.resolve(window.google.maps);
  if (loadPromise) return loadPromise;

  loadPromise = (async () => {
    let key = "";
    try {
      const cfg = await apiFetch("/public-config/", { auth: false });
      key = (cfg && cfg.google_maps_browser_key) || "";
    } catch {
      // fall through to the "not configured" error below
    }
    if (!key) throw new Error("Google Maps browser key not configured");

    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly`;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Failed to load Google Maps"));
      document.head.append(script);
    });
    return window.google.maps;
  })();

  return loadPromise;
}
