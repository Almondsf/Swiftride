from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import Ride, RideOffer
from .matching import offer_to_nearest_driver, OFFER_TIMEOUT

# when nobody is free, keep looking for ~2 minutes before giving up
MATCH_RETRY_DELAY_SECONDS = 15
MAX_MATCH_ATTEMPTS = 8

@shared_task
def find_driver_for_ride(ride_id, attempt=1):
    offer = None
    with transaction.atomic():
        try:
            ride = Ride.objects.select_for_update().get(id=ride_id)
        except Ride.DoesNotExist:
            return

        if ride.status != 'requested':
            return

        # a driver is already deciding; their accept/decline/expiry re-runs this
        if ride.offers.filter(status='pending', expires_at__gt=timezone.now()).exists():
            return

        offer = offer_to_nearest_driver(ride)
        if not offer and attempt >= MAX_MATCH_ATTEMPTS:
            ride.status = 'cancelled'
            ride.save(update_fields=['status', 'updated_at'])
            return

    if offer:
        expire_offer.apply_async(args=[offer.id], countdown=OFFER_TIMEOUT.total_seconds())
    else:
        find_driver_for_ride.apply_async(args=[ride_id, attempt + 1], countdown=MATCH_RETRY_DELAY_SECONDS)


@shared_task
def expire_offer(offer_id):
    expired = RideOffer.objects.filter(id=offer_id, status='pending').update(status='expired')
    if expired:
        offer = RideOffer.objects.get(id=offer_id)
        find_driver_for_ride.delay(offer.ride_id)
