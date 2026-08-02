"""Offline geography: place lookup and distance estimation with no API key.

The Google Maps path in `maps.py` is always preferred when it is configured and
answering. This module is what keeps the system usable without it -- a fresh
checkout with an empty `GOOGLE_MAPS_API_KEY`, a project whose billing lapsed, or
an outage mid-shift. Everything it produces is an *estimate*, and every record
built from it carries `distance_estimated=True` so an operator can tell a
measured mileage from a computed one before it reaches an invoice.

Two approximations are made, both deliberate:

* **Address -> coordinates.** There is no street-level data offline, so an
  address resolves to its city's centre plus a small deterministic offset
  derived from the address text. The offset keeps two addresses in the same town
  from collapsing onto one point (which would price every in-town trip at zero
  miles) and is stable, so the same address always lands on the same spot.
* **Coordinates -> driving distance.** Great-circle distance scaled by a road
  circuity factor. Roads are not straight lines; 1.25 is the usual planning
  figure for a rural grid like North Dakota's.
"""

import hashlib
import math
import re
from decimal import Decimal

# Great-circle radius in miles.
_EARTH_RADIUS_MILES = 3958.7613

# Driving distance / straight-line distance, by trip length. Circuity falls as
# trips get longer: a cross-town run is boxed around North Dakota's section-line
# grid, while anything over ~50 miles is almost certainly following a trunk
# highway (I-94, US-2, US-83) that already runs close to straight. A single flat
# factor overstates the long ones badly -- Bismarck to Fargo is 189 straight-line
# miles and 193 by road, so 1.25 would bill 43 miles that nobody drove.
_CIRCUITY_BANDS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("10"), Decimal("1.35")),
    (Decimal("50"), Decimal("1.22")),
)
_LONG_HAUL_CIRCUITY = Decimal("1.10")


def road_circuity_factor(straight_miles: Decimal) -> Decimal:
    for limit, factor in _CIRCUITY_BANDS:
        if straight_miles < limit:
            return factor
    return _LONG_HAUL_CIRCUITY


# Speed model for the duration estimate: the first few miles are in-town, the
# rest is highway.
_TOWN_MILES = Decimal("5")
_TOWN_MPH = Decimal("25")
_HIGHWAY_MPH = Decimal("55")

# Half-width of the deterministic per-address offset, in degrees. ~2.4 miles at
# North Dakota's latitude in both axes, which is the right order of magnitude
# for "somewhere in this town".
_JITTER_LAT_DEGREES = 0.035
_JITTER_LNG_DEGREES = 0.050

# City centres for the service region: every North Dakota community with a
# clinic, hospital, dialysis centre or care home a rider is plausibly travelling
# to or from, plus the border towns ND riders are routinely referred into.
ND_PLACES: dict[str, tuple[float, float]] = {
    "AMENIA": (47.0272, -97.2237),
    "ARGUSVILLE": (47.0511, -96.9414),
    "ARTHUR": (47.1039, -97.2179),
    "ASHLEY": (46.0339, -99.3701),
    "BEACH": (46.9169, -104.0035),
    "BELCOURT": (48.8419, -99.7454),
    "BELFIELD": (46.8886, -103.1907),
    "BERTHOLD": (48.3172, -101.7357),
    "BEULAH": (47.2633, -101.7779),
    "BISMARCK": (46.8083, -100.7837),
    "BOTTINEAU": (48.8272, -100.4457),
    "BOWBELLS": (48.8036, -102.2454),
    "BOWMAN": (46.1828, -103.3963),
    "BUFFALO": (46.9222, -97.5479),
    "BUXTON": (47.6042, -97.0996),
    "CANDO": (48.4886, -99.2093),
    "CARRINGTON": (47.4497, -99.1262),
    "CASSELTON": (46.9008, -97.2117),
    "CAVALIER": (48.7947, -97.6223),
    "CENTER": (47.1161, -101.2996),
    "COOPERSTOWN": (47.4442, -98.1240),
    "CROSBY": (48.9136, -103.2946),
    "DEVILS LAKE": (48.1128, -98.8651),
    "DICKINSON": (46.8792, -102.7896),
    "DRAYTON": (48.5719, -97.1770),
    "DUNSEITH": (48.8258, -100.0599),
    "EDGELEY": (46.3572, -98.7115),
    "EDMORE": (48.4103, -98.4448),
    "ELGIN": (46.4013, -101.8452),
    "ELLENDALE": (45.8836, -98.5231),
    "EMERADO": (47.9294, -97.3620),
    "ENDERLIN": (46.6242, -97.6015),
    "FARGO": (46.8772, -96.7898),
    "FESSENDEN": (47.6497, -99.6240),
    "FINLEY": (47.5147, -97.8390),
    "FORMAN": (46.1097, -97.6376),
    "FORT YATES": (46.0844, -100.6296),
    "GARRISON": (47.6533, -101.4171),
    "GILBY": (48.0483, -97.4643),
    "GLEN ULLIN": (46.8144, -101.8296),
    "GRAFTON": (48.4128, -97.4106),
    "GRAND FORKS": (47.9253, -97.0329),
    "GWINNER": (46.1878, -97.6612),
    "HANKINSON": (46.0703, -96.8990),
    "HARVEY": (47.7719, -99.9337),
    "HATTON": (47.6414, -97.4570),
    "HAZEN": (47.2919, -101.6265),
    "HEBRON": (46.9002, -102.0393),
    "HETTINGER": (46.0006, -102.6396),
    "HILLSBORO": (47.4014, -97.0623),
    "HOOPLE": (48.5347, -97.6390),
    "HOPE": (47.3253, -97.7182),
    "HORACE": (46.7580, -96.9020),
    "HUNTER": (47.1961, -97.2015),
    "JAMESTOWN": (46.9105, -98.7084),
    "KENMARE": (48.6753, -102.0793),
    "KILLDEER": (47.3705, -102.7532),
    "KINDRED": (46.6467, -97.0140),
    "LAKOTA": (48.0428, -98.3437),
    "LANGDON": (48.7597, -98.3684),
    "LARIMORE": (47.9061, -97.6262),
    "LIDGERWOOD": (46.0714, -97.1509),
    "LINCOLN": (46.7772, -100.7460),
    "LINTON": (46.2669, -100.2321),
    "LISBON": (46.4386, -97.6812),
    "MANDAN": (46.8267, -100.8896),
    "MANVEL": (48.0797, -97.1793),
    "MAPLETON": (46.8961, -97.0501),
    "MAX": (47.8194, -101.2938),
    "MAYVILLE": (47.4986, -97.3237),
    "MICHIGAN": (48.0272, -98.1287),
    "MILNOR": (46.2603, -97.4553),
    "MINNEWAUKAN": (48.0678, -99.2504),
    "MINOT": (48.2330, -101.2923),
    "MOHALL": (48.7639, -101.5185),
    "MOTT": (46.3728, -102.3243),
    "MUNICH": (48.6683, -98.8318),
    "NAPOLEON": (46.5064, -99.7712),
    "NECHE": (48.9908, -97.5537),
    "NEW ENGLAND": (46.5361, -102.8663),
    "NEW ROCKFORD": (47.6805, -99.1382),
    "NEW SALEM": (46.8447, -101.4118),
    "NEW TOWN": (47.9805, -102.4907),
    "NORTHWOOD": (47.7361, -97.5695),
    "OAKES": (46.1386, -98.0917),
    "PAGE": (47.1600, -97.5715),
    "PARK RIVER": (48.3969, -97.7351),
    "PARSHALL": (47.9528, -102.1346),
    "POWERS LAKE": (48.5636, -102.6390),
    "RAY": (48.3411, -103.1655),
    "REYNOLDS": (47.6708, -97.1004),
    "RIVERDALE": (47.4980, -101.3707),
    "ROLLA": (48.8586, -99.6162),
    "RUGBY": (48.3697, -99.9962),
    "RUTLAND": (46.0522, -97.5079),
    "ST JOHN": (48.9450, -99.7112),
    "STANLEY": (48.3175, -102.3893),
    "STANTON": (47.3230, -101.3796),
    "STEELE": (46.8558, -99.9154),
    "SURREY": (48.2361, -101.1360),
    "THOMPSON": (47.7758, -97.1082),
    "TIOGA": (48.3961, -102.9382),
    "TOWER CITY": (46.9256, -97.6737),
    "TURTLE LAKE": (47.5197, -100.8888),
    "UNDERWOOD": (47.4530, -101.1382),
    "VALLEY CITY": (46.9233, -98.0032),
    "VELVA": (48.0578, -100.9346),
    "WAHPETON": (46.2652, -96.6059),
    "WALHALLA": (48.9219, -97.9184),
    "WASHBURN": (47.2903, -101.0293),
    "WATFORD CITY": (47.8022, -103.2833),
    "WEST FARGO": (46.8747, -96.9003),
    "WESTHOPE": (48.9111, -101.0210),
    "WILLISTON": (48.1470, -103.6180),
    "WISHEK": (46.2578, -99.5545),
    # Border communities ND riders are referred into for care.
    "BRECKENRIDGE": (46.2633, -96.5878),
    "EAST GRAND FORKS": (47.9297, -97.0242),
    "MOORHEAD": (46.8738, -96.7678),
    "SISSETON": (45.6647, -97.0489),
}

_PUNCTUATION = re.compile(r"[^A-Z0-9 ]+")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Upper-case, strip punctuation, collapse whitespace.

    `St. John` and `ST JOHN` have to reach the same key, and the same address
    typed with and without a trailing period has to hash to the same offset.
    """
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", (text or "").upper())).strip()


def find_place(address: str) -> str | None:
    """Name of the known place this address sits in, or None.

    Longest match wins, so `WEST FARGO` beats `FARGO` and `EAST GRAND FORKS`
    beats `GRAND FORKS` -- a shorter name is often a substring of a longer one.
    """
    haystack = f" {normalize(address)} "
    best: str | None = None
    for name in ND_PLACES:
        if f" {name} " in haystack and (best is None or len(name) > len(best)):
            best = name
    return best


def _offsets(address: str) -> tuple[float, float]:
    """Two stable values in [-1, 1) derived from the address text."""
    digest = hashlib.sha256(normalize(address).encode()).digest()
    lat_raw = int.from_bytes(digest[:4], "big")
    lng_raw = int.from_bytes(digest[4:8], "big")
    scale = 2**32
    return (lat_raw / scale) * 2 - 1, (lng_raw / scale) * 2 - 1


def locate(address: str) -> tuple[Decimal, Decimal] | None:
    """Estimated (lat, lng) for an address, or None if its town is unknown."""
    place = find_place(address)
    if place is None:
        return None
    base_lat, base_lng = ND_PLACES[place]
    lat_offset, lng_offset = _offsets(address)
    lat = base_lat + lat_offset * _JITTER_LAT_DEGREES
    lng = base_lng + lng_offset * _JITTER_LNG_DEGREES
    return Decimal(f"{lat:.6f}"), Decimal(f"{lng:.6f}")


def haversine_miles(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> Decimal:
    """Great-circle distance in miles between two (lat, lng) points."""
    lat1, lng1 = math.radians(float(origin[0])), math.radians(float(origin[1]))
    lat2, lng2 = math.radians(float(destination[0])), math.radians(float(destination[1]))
    delta_lat, delta_lng = lat2 - lat1, lng2 - lng1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    miles = 2 * _EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))
    return Decimal(f"{miles:.6f}")


def estimate_minutes(miles: Decimal) -> int:
    """Driving time for a road distance, in whole minutes (never below 5)."""
    town = min(miles, _TOWN_MILES)
    highway = max(miles - _TOWN_MILES, Decimal("0"))
    minutes = (town / _TOWN_MPH + highway / _HIGHWAY_MPH) * 60
    return max(5, int(minutes.quantize(Decimal("1"))))


def estimate_route(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> tuple[Decimal, int]:
    """Estimated (road miles, duration minutes) between two points."""
    straight = haversine_miles(origin, destination)
    miles = (straight * road_circuity_factor(straight)).quantize(Decimal("0.01"))
    return miles, estimate_minutes(miles)
