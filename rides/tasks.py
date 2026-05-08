from celery import shared_task
from .models import Ride
from accounts.models import CustomUser

@shared_task
def find_driver_for_ride(ride_id):
    try:
        ride = Ride.objects.get(id=ride_id)
        
        # find an available driver
        driver = CustomUser.objects.filter(
            role='driver'
        ).exclude(
            drives__status__in=['accepted', 'in_progress']
        ).first()
        
        if driver:
            ride.driver = driver
            ride.status = 'accepted'
            ride.save()
        else:
            ride.status = 'cancelled'
            ride.save()
            
    except Ride.DoesNotExist:
        pass