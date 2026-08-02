"""Applying operator policy: service-area coverage and message templates."""

from decimal import Decimal

from apps.trips.services import geo

from .models import ServiceArea, ServiceAreaKind, SystemSetting

# How far from a named town's centre still counts as being in that town. Only
# used when the address text doesn't name the town itself -- a Google-resolved
# address may arrive as "300 N 7th St" with the city stripped, and refusing that
# would be wrong.
PLACE_TOLERANCE_MILES = Decimal("12")


class ServiceAreaError(Exception):
    """Raised when an address is outside every configured service area."""


def active_areas():
    return list(ServiceArea.objects.filter(is_active=True))


def _covered_by(area: ServiceArea, address: str, point) -> bool:
    if area.kind == ServiceAreaKind.PLACE:
        target = geo.normalize(area.place)
        named = geo.find_place(address)
        if named is not None and named == target:
            return True
        # Fall back to proximity when the address text doesn't name its town.
        centre = geo.ND_PLACES.get(target)
        if centre is None or point is None:
            return False
        return (
            geo.haversine_miles(point, (Decimal(str(centre[0])), Decimal(str(centre[1]))))
            <= PLACE_TOLERANCE_MILES
        )

    if point is None:
        return False
    return geo.haversine_miles(point, (area.center_lat, area.center_lng)) <= area.radius_miles


def is_covered(address: str, point=None, areas=None) -> bool:
    """Is this address inside the service area?

    True when no areas are configured -- an operator who hasn't drawn a boundary
    hasn't asked us to turn anyone away.
    """
    areas = active_areas() if areas is None else areas
    if not areas:
        return True
    return any(_covered_by(area, address, point) for area in areas)


def check_service_area(pickup_address, pickup_point, dropoff_address, dropoff_point):
    """Raise ServiceAreaError naming whichever end of the trip is out of area."""
    setting = SystemSetting.load()
    if not setting.enforce_service_area:
        return

    areas = active_areas()
    if not areas:
        return

    outside = []
    if not is_covered(pickup_address, pickup_point, areas):
        outside.append(("pickup_address", pickup_address))
    if not is_covered(dropoff_address, dropoff_point, areas):
        outside.append(("dropoff_address", dropoff_address))

    if outside:
        served = ", ".join(area.name for area in areas)
        raise ServiceAreaError(
            {
                field: (
                    f"{value} is outside the area Gentle Care Transit serves. "
                    f"We currently cover: {served}."
                )
                for field, value in outside
            }
        )


def render_template(field: str, default: str, context: dict) -> str:
    """An operator-edited message body, or the wording built into the app.

    A template referencing a placeholder that doesn't exist yields the literal
    text rather than an error -- a typo on the settings screen must not stop a
    trip notification from going out.
    """
    template = (getattr(SystemSetting.load(), field, "") or "").strip()
    if not template:
        return default
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError):
        return template
