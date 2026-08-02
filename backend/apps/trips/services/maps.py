import logging
from dataclasses import dataclass
from decimal import Decimal

import googlemaps
import requests
from django.conf import settings

from . import geo

logger = logging.getLogger(__name__)

# Routes API v2 (computeRoutes) replaces the legacy Distance Matrix API, which
# Google no longer enables for new projects. The googlemaps client doesn't cover
# it, so this one call is made over plain HTTP.
ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
_METERS_PER_MILE = Decimal("1609.34")


class GeocodingError(Exception):
    """Raised when an address can't be geocoded or a distance can't be computed."""


@dataclass(frozen=True)
class RouteResolution:
    """Everything booking needs to place a trip on the map and price it.

    `estimated` is False only when Google measured every part of this result.
    It is stored on the trip so an operator reviewing an invoice can tell a
    measured mileage from a computed one.
    """

    pickup_lat: Decimal
    pickup_lng: Decimal
    dropoff_lat: Decimal
    dropoff_lng: Decimal
    miles: Decimal
    duration_minutes: int
    estimated: bool


def offline_fallback_enabled() -> bool:
    return getattr(settings, "MAPS_OFFLINE_FALLBACK", True)


def _client() -> googlemaps.Client:
    if not settings.GOOGLE_MAPS_API_KEY:
        raise GeocodingError("GOOGLE_MAPS_API_KEY is not configured.")
    return googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY, timeout=5)


# Everything the googlemaps client can raise for an upstream problem (denied key,
# billing disabled, quota, timeout, transport). Callers only handle GeocodingError,
# so these are translated rather than allowed to surface as a 500.
_GOOGLEMAPS_ERRORS = (
    googlemaps.exceptions.ApiError,
    googlemaps.exceptions.TransportError,  # HTTPError subclasses this
    googlemaps.exceptions.Timeout,
)


def _google_geocode(address: str) -> tuple[Decimal, Decimal]:
    """Measured (lat, lng) from Google, or GeocodingError."""
    try:
        results = _client().geocode(address)
    except _GOOGLEMAPS_ERRORS as exc:
        raise GeocodingError(f"Address lookup is unavailable right now: {exc}") from exc
    if not results:
        raise GeocodingError(f"Could not geocode address: {address!r}")
    location = results[0]["geometry"]["location"]
    return Decimal(str(location["lat"])), Decimal(str(location["lng"]))


def geocode_address(address: str) -> tuple[Decimal, Decimal]:
    """Return (lat, lng) for a free-text address.

    Prefers Google. Falls back to the offline gazetteer when Google isn't
    configured or isn't answering, so the system stays usable without a key.
    Use `resolve_route` where the caller needs to record *which* of the two
    produced the answer.
    """
    return _locate(address)[0]


def _locate(address: str) -> tuple[tuple[Decimal, Decimal], bool]:
    """((lat, lng), estimated) for an address."""
    if settings.GOOGLE_MAPS_API_KEY:
        try:
            return _google_geocode(address), False
        except GeocodingError as exc:
            if not offline_fallback_enabled():
                raise
            logger.warning("Geocoding %r via Google failed (%s); estimating offline.", address, exc)
    elif not offline_fallback_enabled():
        raise GeocodingError("GOOGLE_MAPS_API_KEY is not configured.")

    point = geo.locate(address)
    if point is None:
        raise GeocodingError(
            f"Could not find {address!r}. Include the city and state, "
            "for example '300 N 7th St, Bismarck, ND'."
        )
    return point, True


def _waypoint(point: tuple[Decimal, Decimal]) -> dict:
    return {"location": {"latLng": {"latitude": float(point[0]), "longitude": float(point[1])}}}


def _google_distance(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> tuple[Decimal, int]:
    """Measured (miles, duration_minutes) from the Routes API, or GeocodingError."""
    if not settings.GOOGLE_MAPS_API_KEY:
        raise GeocodingError("GOOGLE_MAPS_API_KEY is not configured.")

    payload = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": "DRIVE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        # FieldMask keeps the response minimal -- only the two fields we use.
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
    }
    try:
        response = requests.post(ROUTES_ENDPOINT, json=payload, headers=headers, timeout=5)
    except requests.RequestException as exc:
        raise GeocodingError(f"Routing request failed: {exc}") from exc

    if response.status_code != 200:
        raise GeocodingError(
            f"Could not compute distance: HTTP {response.status_code} {response.text[:200]}"
        )

    routes = (response.json() or {}).get("routes") or []
    if not routes:
        raise GeocodingError("Could not compute distance: no route found.")

    route = routes[0]
    meters = route.get("distanceMeters")
    if meters is None:
        raise GeocodingError("Could not compute distance: missing distance.")

    # Routes API returns duration as a protobuf-style string like "1234s".
    seconds = int(str(route.get("duration", "0s")).rstrip("s") or 0)
    miles = Decimal(meters) / _METERS_PER_MILE
    return miles.quantize(Decimal("0.01")), round(seconds / 60)


def _route(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> tuple[Decimal, int, bool]:
    """(miles, duration_minutes, estimated) between two points."""
    if settings.GOOGLE_MAPS_API_KEY:
        try:
            miles, minutes = _google_distance(origin, destination)
            return miles, minutes, False
        except GeocodingError as exc:
            if not offline_fallback_enabled():
                raise
            logger.warning("Routing via Google failed (%s); estimating offline.", exc)
    elif not offline_fallback_enabled():
        raise GeocodingError("GOOGLE_MAPS_API_KEY is not configured.")

    miles, minutes = geo.estimate_route(origin, destination)
    return miles, minutes, True


def get_distance(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> tuple[Decimal, int]:
    """Return (miles, duration_minutes) between two (lat, lng) points.

    Prefers the Routes API and falls back to a haversine estimate. Signature is
    unchanged from the legacy Distance Matrix version.
    """
    miles, minutes, _ = _route(origin, destination)
    return miles, minutes


def resolve_route(pickup_address: str, dropoff_address: str) -> RouteResolution:
    """Geocode both ends and measure the drive between them.

    This is the single entry point booking uses, because it is the only caller
    that must record whether the numbers were measured or estimated. A result is
    `estimated` if *any* of its three lookups fell back -- an exact drive between
    two guessed points is still a guess.
    """
    (pickup_lat, pickup_lng), pickup_estimated = _locate(pickup_address)
    (dropoff_lat, dropoff_lng), dropoff_estimated = _locate(dropoff_address)
    miles, minutes, route_estimated = _route((pickup_lat, pickup_lng), (dropoff_lat, dropoff_lng))
    return RouteResolution(
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        miles=miles,
        duration_minutes=minutes,
        estimated=pickup_estimated or dropoff_estimated or route_estimated,
    )
