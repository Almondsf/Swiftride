import math
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from geopy.distance import geodesic

from tracking.models import DriverLocation
from .models import Ride, RideOffer
from .ratings import low_rated_driver_ids

SEARCH_RADIUS_KM = 10
# a driver who hasn't reported in this long is treated as gone
LOCATION_STALE_AFTER = timedelta(minutes=2)
# how long a driver has to accept an offer before it moves on
OFFER_TIMEOUT = timedelta(seconds=20)
ACTIVE_STATUSES = ['accepted', 'in_progress']


def busy_driver_ids():
    """Drivers on a ride or currently deciding on an offer."""
    on_ride = Ride.objects.filter(
        status__in=ACTIVE_STATUSES, driver__isnull=False
    ).values('driver_id')
    deciding = RideOffer.objects.filter(
        status='pending', expires_at__gt=timezone.now()
    ).values('driver_id')
    return on_ride, deciding


def driver_is_busy(driver_id):
    on_ride, deciding = busy_driver_ids()
    return on_ride.filter(driver_id=driver_id).exists() or deciding.filter(driver_id=driver_id).exists()


def bounding_box(lat, lng, radius_km):
    """(lat_range, lng_range) of a box enclosing the circle; a cheap DB prefilter."""
    lat, lng = float(lat), float(lng)
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return (lat - lat_delta, lat + lat_delta), (lng - lng_delta, lng + lng_delta)


def nearby_driver_locations(lat, lng, radius_km=SEARCH_RADIUS_KM, exclude_driver_ids=()):
    """Available drivers within radius_km of (lat, lng), nearest first."""
    lat, lng = float(lat), float(lng)

    # cheap bounding-box filter in the DB, exact distance in Python
    lat_range, lng_range = bounding_box(lat, lng, radius_km)

    on_ride, deciding = busy_driver_ids()
    candidates = DriverLocation.objects.filter(
        is_online=True,
        updated_at__gte=timezone.now() - LOCATION_STALE_AFTER,
        latitude__range=lat_range,
        longitude__range=lng_range,
    ).exclude(
        driver_id__in=on_ride
    ).exclude(
        driver_id__in=deciding
    ).exclude(
        driver_id__in=low_rated_driver_ids()
    ).exclude(
        driver_id__in=list(exclude_driver_ids)
    ).select_related('driver')

    ranked = []
    for location in candidates:
        distance = geodesic((lat, lng), (location.latitude, location.longitude)).km
        if distance <= radius_km:
            ranked.append((distance, location))
    ranked.sort(key=lambda pair: pair[0])
    return [location for _, location in ranked]


def offer_to_nearest_driver(ride):
    """Offer the ride to the closest available driver it hasn't been offered to yet.

    Returns the new RideOffer, or None if nobody is available.
    """
    already_offered = list(ride.offers.values_list('driver_id', flat=True))
    for location in nearby_driver_locations(ride.pickup_lat, ride.pickup_lng, exclude_driver_ids=already_offered):
        with transaction.atomic():
            # lock the driver so two rides being matched at once can't both claim them
            DriverLocation.objects.select_for_update().get(pk=location.pk)
            if driver_is_busy(location.driver_id):
                continue
            return RideOffer.objects.create(
                ride=ride, driver=location.driver, expires_at=timezone.now() + OFFER_TIMEOUT
            )
    return None
