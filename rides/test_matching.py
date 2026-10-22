from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from tracking.models import DriverLocation
from .matching import assign_nearest_driver
from .models import Ride
from .tasks import find_driver_for_ride

# Yaba, Lagos
PICKUP = (Decimal('6.509500'), Decimal('3.371100'))


class MatchingTests(TestCase):
    def setUp(self):
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.phone = 10

    def make_driver(self, lat, lng, is_online=True):
        self.phone += 1
        driver = CustomUser.objects.create_user(
            email=f'd{self.phone}@test.com', phone_number=f'08000000{self.phone}', role='driver'
        )
        DriverLocation.objects.create(driver=driver, latitude=lat, longitude=lng, is_online=is_online)
        return driver

    def make_ride(self):
        return Ride.objects.create(
            rider=self.rider, pickup_location='Yaba', dropoff_location='Ikeja',
            pickup_lat=PICKUP[0], pickup_lng=PICKUP[1],
            dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'),
        )

    def test_picks_nearest_driver(self):
        self.make_driver(6.55, 3.38)            # ~4.5km
        near = self.make_driver(6.512, 3.372)   # ~0.3km
        self.make_driver(6.53, 3.36)            # ~2.6km
        ride = self.make_ride()

        self.assertEqual(assign_nearest_driver(ride), near)
        ride.refresh_from_db()
        self.assertEqual(ride.driver, near)
        self.assertEqual(ride.status, 'accepted')

    def test_skips_offline_stale_busy_and_far_drivers(self):
        self.make_driver(6.5096, 3.3712, is_online=False)
        stale = self.make_driver(6.5097, 3.3712)
        DriverLocation.objects.filter(driver=stale).update(updated_at=timezone.now() - timedelta(minutes=10))
        busy = self.make_driver(6.5098, 3.3712)
        Ride.objects.create(rider=self.rider, driver=busy, status='in_progress', pickup_location='X', dropoff_location='Y')
        self.make_driver(6.75, 3.37)  # ~27km away
        available = self.make_driver(6.52, 3.38)

        self.assertEqual(assign_nearest_driver(self.make_ride()), available)

    def test_no_driver_available(self):
        self.make_driver(6.5096, 3.3712, is_online=False)
        ride = self.make_ride()
        self.assertIsNone(assign_nearest_driver(ride))
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'requested')

    def test_does_not_overwrite_cancelled_ride(self):
        self.make_driver(6.512, 3.372)
        ride = self.make_ride()
        Ride.objects.filter(pk=ride.pk).update(status='cancelled')
        self.assertIsNone(assign_nearest_driver(ride))
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'cancelled')
        self.assertIsNone(ride.driver)

    def test_driver_not_given_two_rides(self):
        self.make_driver(6.512, 3.372)
        first, second = self.make_ride(), self.make_ride()
        self.assertIsNotNone(assign_nearest_driver(first))
        self.assertIsNone(assign_nearest_driver(second))

    def test_task_cancels_after_retries_run_out(self):
        ride = self.make_ride()
        # eager apply runs the retries inline, ignoring the countdown
        find_driver_for_ride.apply(args=[ride.id])
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'cancelled')

    def test_task_assigns_driver(self):
        driver = self.make_driver(6.512, 3.372)
        ride = self.make_ride()
        find_driver_for_ride.apply(args=[ride.id])
        ride.refresh_from_db()
        self.assertEqual(ride.driver, driver)
