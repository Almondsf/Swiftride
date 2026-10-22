import math
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from geopy.distance import geodesic

from tracking.models import DriverLocation
from .models import Ride

SEARCH_RADIUS_KM = 10
# a driver who hasn't reported in this long is treated as gone
LOCATION_STALE_AFTER = timedelta(minutes=2)
ACTIVE_STATUSES = ['accepted', 'in_progress']


def nearby_driver_locations(lat, lng, radius_km=SEARCH_RADIUS_KM):
    """Available drivers within radius_km of (lat, lng), nearest first."""
    lat, lng = float(lat), float(lng)

    # cheap bounding-box filter in the DB, exact distance in Python
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))

    candidates = DriverLocation.objects.filter(
        is_online=True,
        updated_at__gte=timezone.now() - LOCATION_STALE_AFTER,
        latitude__range=(lat - lat_delta, lat + lat_delta),
        longitude__range=(lng - lng_delta, lng + lng_delta),
    ).exclude(
        driver__drives__status__in=ACTIVE_STATUSES
    ).select_related('driver')

    ranked = []
    for location in candidates:
        distance = geodesic((lat, lng), (location.latitude, location.longitude)).km
        if distance <= radius_km:
            ranked.append((distance, location))
    ranked.sort(key=lambda pair: pair[0])
    return [location for _, location in ranked]


def assign_nearest_driver(ride):
    """Assign the closest available driver to a requested ride.

    Returns the driver, or None if nobody is free (or the ride is no longer
    waiting for a driver).
    """
    for location in nearby_driver_locations(ride.pickup_lat, ride.pickup_lng):
        with transaction.atomic():
            # lock the driver so two rides being matched at once can't both get them
            DriverLocation.objects.select_for_update().get(pk=location.pk)
            if Ride.objects.filter(driver=location.driver, status__in=ACTIVE_STATUSES).exists():
                continue

            updated = Ride.objects.filter(pk=ride.pk, status='requested').update(
                driver=location.driver, status='accepted', updated_at=timezone.now()
            )
            if not updated:
                # cancelled or picked up manually in the meantime
                return None
            return location.driver
    return None
