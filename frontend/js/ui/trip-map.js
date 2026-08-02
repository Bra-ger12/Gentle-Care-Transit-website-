import { el } from "./dom.js";
import { loadGoogleMaps } from "./maps.js";

// Bismarck, ND — the service area's centre, used until real coordinates arrive.
const DEFAULT_CENTER = { lat: 46.8083, lng: -100.7837 };

/**
 * A Google Map panel that degrades to a note instead of an empty grey box when no
 * browser key is configured (or the script fails to load).
 *
 * Returns `{ element, whenReady }`. Append `element` to the page, then await
 * `whenReady`: it resolves to `{ maps, map }`, or to `null` when the map is
 * unavailable — it never rejects, so callers don't need a catch.
 */
export function mapPanel({ className = "ops-map", zoom = 11, center = DEFAULT_CENTER } = {}) {
  const element = el("div", { class: className });

  const whenReady = loadGoogleMaps()
    .then((maps) => ({
      maps,
      map: new maps.Map(element, { center, zoom, disableDefaultUI: true, zoomControl: true }),
    }))
    .catch(() => {
      const fallback = el("p", {
        class: "track__map-fallback",
        text: "Map unavailable (Google Maps browser key not configured).",
      });
      if (element.isConnected) element.replaceWith(fallback);
      else element.replaceChildren(fallback);
      return null;
    });

  return { element, whenReady };
}

/** A filled circle marker icon — used for live vehicle positions. */
export function vehicleDot(maps, color = "#2563eb") {
  return {
    path: maps.SymbolPath.CIRCLE,
    scale: 8,
    fillColor: color,
    fillOpacity: 1,
    strokeColor: "#ffffff",
    strokeWeight: 2,
  };
}

/** Frame the map around `positions`; a single position just centres on it. */
export function fitTo(maps, map, positions) {
  const points = positions.filter((p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lng));
  if (points.length === 0) return;
  if (points.length === 1) {
    map.setCenter(points[0]);
    return;
  }
  const bounds = new maps.LatLngBounds();
  points.forEach((p) => bounds.extend(p));
  map.fitBounds(bounds);
}

/** `{ lat, lng }` from a trip's pickup/drop-off pair, or null when ungeocoded. */
export function tripPoint(trip, kind = "pickup") {
  const lat = Number(trip[`${kind}_lat`]);
  const lng = Number(trip[`${kind}_lng`]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat, lng };
}
