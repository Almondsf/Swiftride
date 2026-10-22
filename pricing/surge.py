"""Surge pricing from live demand (open ride requests) vs supply (free drivers) nearby."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.cache import cache
from django.utils import timezone

from rides.matching import bounding_box, nearby_driver_locations
from rides.models import Ride

SURGE_RADIUS_KM = 3
# only recent requests count as demand; older ones are stale or about to be cancelled
DEMAND_WINDOW = timedelta(minutes=10)
MAX_SURGE = Decimal('3.0')
# how much of the demand/supply imbalance turns into surge: ratio 3 -> 2.0x
SURGE_SENSITIVITY = Decimal('0.5')
CACHE_SECONDS = 60
# cells of 0.01 degrees (~1.1km) share a cached surge value
CELL_PRECISION = 2


def calculate_surge(demand, supply):
    """1.0 when supply keeps up with demand, rising with the imbalance, capped at MAX_SURGE."""
    ratio = Decimal(demand) / Decimal(max(supply, 1))
    if ratio <= 1:
        return Decimal('1.0')
    surge = 1 + (ratio - 1) * SURGE_SENSITIVITY
    return min(surge, MAX_SURGE).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def demand_near(lat, lng, radius_km=SURGE_RADIUS_KM):
    lat_range, lng_range = bounding_box(lat, lng, radius_km)
    return Ride.objects.filter(
        status='requested',
        created_at__gte=timezone.now() - DEMAND_WINDOW,
        pickup_lat__range=lat_range,
        pickup_lng__range=lng_range,
    ).count()


def supply_near(lat, lng, radius_km=SURGE_RADIUS_KM):
    return len(nearby_driver_locations(lat, lng, radius_km=radius_km))


def surge_cache_key(lat, lng):
    return f'surge:{round(float(lat), CELL_PRECISION)}:{round(float(lng), CELL_PRECISION)}'


def current_surge(lat, lng):
    """Surge multiplier at (lat, lng), cached per grid cell."""
    key = surge_cache_key(lat, lng)
    surge = cache.get(key)
    if surge is None:
        surge = calculate_surge(demand_near(lat, lng), supply_near(lat, lng))
        cache.set(key, surge, CACHE_SECONDS)
    return surge
