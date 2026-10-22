from celery import shared_task
from .models import Ride
from .matching import assign_nearest_driver

# keep looking for ~2 minutes before giving up
MATCH_RETRY_DELAY_SECONDS = 15
MAX_MATCH_ATTEMPTS = 8

@shared_task(bind=True, max_retries=MAX_MATCH_ATTEMPTS - 1)
def find_driver_for_ride(self, ride_id):
    try:
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        return

    if ride.status != 'requested':
        return

    if assign_nearest_driver(ride):
        return

    if self.request.retries >= self.max_retries:
        Ride.objects.filter(pk=ride.pk, status='requested').update(status='cancelled')
        return

    raise self.retry(countdown=MATCH_RETRY_DELAY_SECONDS)
