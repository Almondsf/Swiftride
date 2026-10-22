"""Push ride events to riders and drivers over the notifications WebSocket."""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .eta import estimate_eta

logger = logging.getLogger(__name__)


def user_group(user_id):
    return f'user_{user_id}'


def send_to_user(user_id, event, data):
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(user_group(user_id), {'type': 'notify', 'event': event, 'data': data})
    except Exception:
        # a push failing (e.g. Redis down) shouldn't fail the request that triggered it
        logger.exception('Failed to send %s to user %s', event, user_id)


def notify_ride_status(ride, **extra):
    data = {
        'ride_id': ride.id,
        'status': ride.status,
        'driver_id': ride.driver_id,
        'fare': str(ride.fare) if ride.fare is not None else None,
        **extra,
    }
    for user_id in {ride.rider_id, ride.driver_id} - {None}:
        send_to_user(user_id, 'ride.status', data)


def notify_offer(offer):
    ride = offer.ride
    data = {
        'offer_id': offer.id,
        'ride_id': ride.id,
        'pickup_location': ride.pickup_location,
        'dropoff_location': ride.dropoff_location,
        'pickup_lat': str(ride.pickup_lat),
        'pickup_lng': str(ride.pickup_lng),
        'surge_multiplier': str(ride.surge_multiplier),
        'expires_at': offer.expires_at.isoformat(),
    }
    location = getattr(offer.driver, 'location', None)
    if location:
        # how far the driver is from the pickup, to help them decide
        data.update(estimate_eta(location.latitude, location.longitude, ride.pickup_lat, ride.pickup_lng))
    send_to_user(offer.driver_id, 'ride.offer', data)


def notify_offer_withdrawn(driver_id, offer_id, ride_id):
    send_to_user(driver_id, 'ride.offer_withdrawn', {'offer_id': offer_id, 'ride_id': ride_id})
