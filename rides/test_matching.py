from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from tracking.models import DriverLocation
from .matching import offer_to_nearest_driver
from .models import Ride, RideOffer
from .tasks import find_driver_for_ride, expire_offer, MAX_MATCH_ATTEMPTS

# Yaba, Lagos
PICKUP = (Decimal('6.509500'), Decimal('3.371100'))


class MatchingFixtures:
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

    def make_offer(self, ride, driver, **kwargs):
        defaults = dict(expires_at=timezone.now() + timedelta(seconds=20))
        defaults.update(kwargs)
        return RideOffer.objects.create(ride=ride, driver=driver, **defaults)


class OfferToNearestDriverTests(MatchingFixtures, TestCase):
    def test_offers_to_nearest_driver(self):
        self.make_driver(6.55, 3.38)            # ~4.5km
        near = self.make_driver(6.512, 3.372)   # ~0.3km
        self.make_driver(6.53, 3.36)            # ~2.6km
        ride = self.make_ride()

        offer = offer_to_nearest_driver(ride)
        self.assertEqual(offer.driver, near)
        ride.refresh_from_db()
        # offering doesn't assign; the driver still has to accept
        self.assertEqual(ride.status, 'requested')
        self.assertIsNone(ride.driver)

    def test_skips_offline_stale_busy_and_far_drivers(self):
        self.make_driver(6.5096, 3.3712, is_online=False)
        stale = self.make_driver(6.5097, 3.3712)
        DriverLocation.objects.filter(driver=stale).update(updated_at=timezone.now() - timedelta(minutes=10))
        busy = self.make_driver(6.5098, 3.3712)
        Ride.objects.create(rider=self.rider, driver=busy, status='in_progress', pickup_location='X', dropoff_location='Y')
        self.make_driver(6.75, 3.37)  # ~27km away
        available = self.make_driver(6.52, 3.38)

        self.assertEqual(offer_to_nearest_driver(self.make_ride()).driver, available)

    def test_skips_driver_already_deciding_on_another_offer(self):
        deciding = self.make_driver(6.512, 3.372)
        other = self.make_driver(6.53, 3.36)
        self.make_offer(self.make_ride(), deciding)
        self.assertEqual(offer_to_nearest_driver(self.make_ride()).driver, other)

    def test_does_not_reoffer_to_driver_who_declined(self):
        near = self.make_driver(6.512, 3.372)
        next_nearest = self.make_driver(6.53, 3.36)
        ride = self.make_ride()
        self.make_offer(ride, near, status='declined')
        self.assertEqual(offer_to_nearest_driver(ride).driver, next_nearest)

    def test_no_driver_available(self):
        self.make_driver(6.5096, 3.3712, is_online=False)
        self.assertIsNone(offer_to_nearest_driver(self.make_ride()))


@patch('rides.tasks.expire_offer.apply_async')
@patch('rides.tasks.find_driver_for_ride.apply_async')
class FindDriverTaskTests(MatchingFixtures, TestCase):
    def test_creates_offer_and_schedules_expiry(self, mock_retry, mock_expire):
        driver = self.make_driver(6.512, 3.372)
        ride = self.make_ride()
        find_driver_for_ride(ride.id)
        offer = RideOffer.objects.get(ride=ride)
        self.assertEqual(offer.driver, driver)
        mock_expire.assert_called_once_with(args=[offer.id], countdown=20)
        mock_retry.assert_not_called()

    def test_retries_when_nobody_is_free(self, mock_retry, mock_expire):
        ride = self.make_ride()
        find_driver_for_ride(ride.id)
        mock_retry.assert_called_once_with(args=[ride.id, 2], countdown=15)
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'requested')

    def test_cancels_after_last_attempt(self, mock_retry, mock_expire):
        ride = self.make_ride()
        find_driver_for_ride(ride.id, attempt=MAX_MATCH_ATTEMPTS)
        mock_retry.assert_not_called()
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'cancelled')

    def test_does_nothing_while_an_offer_is_pending(self, mock_retry, mock_expire):
        first = self.make_driver(6.512, 3.372)
        self.make_driver(6.53, 3.36)
        ride = self.make_ride()
        self.make_offer(ride, first)
        find_driver_for_ride(ride.id)
        self.assertEqual(ride.offers.count(), 1)
        mock_retry.assert_not_called()

    def test_ignores_rides_no_longer_requested(self, mock_retry, mock_expire):
        self.make_driver(6.512, 3.372)
        ride = self.make_ride()
        Ride.objects.filter(pk=ride.pk).update(status='cancelled')
        find_driver_for_ride(ride.id)
        self.assertFalse(ride.offers.exists())

    @patch('rides.tasks.find_driver_for_ride.delay')
    def test_expiry_moves_on_to_next_driver(self, mock_delay, mock_retry, mock_expire):
        ride = self.make_ride()
        offer = self.make_offer(ride, self.make_driver(6.512, 3.372))
        expire_offer(offer.id)
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'expired')
        mock_delay.assert_called_once_with(ride.id)

    @patch('rides.tasks.find_driver_for_ride.delay')
    def test_expiry_is_noop_after_accept(self, mock_delay, mock_retry, mock_expire):
        offer = self.make_offer(self.make_ride(), self.make_driver(6.512, 3.372), status='accepted')
        expire_offer(offer.id)
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'accepted')
        mock_delay.assert_not_called()


class OfferEndpointTests(MatchingFixtures, APITestCase):
    def setUp(self):
        super().setUp()
        self.driver = self.make_driver(6.512, 3.372)
        self.ride = self.make_ride()
        self.offer = self.make_offer(self.ride, self.driver)
        self.client.force_authenticate(self.driver)

    def test_driver_sees_pending_offers(self):
        response = self.client.get(reverse('ride-offers'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([o['id'] for o in response.data], [self.offer.id])
        self.assertEqual(response.data[0]['ride']['id'], self.ride.id)

    def test_accept_offer_assigns_driver(self):
        response = self.client.post(reverse('accept-offer', args=[self.offer.id]))
        self.assertEqual(response.status_code, 200)
        self.ride.refresh_from_db()
        self.offer.refresh_from_db()
        self.assertEqual(self.ride.driver, self.driver)
        self.assertEqual(self.ride.status, 'accepted')
        self.assertEqual(self.offer.status, 'accepted')

    def test_cannot_accept_expired_offer(self):
        RideOffer.objects.filter(pk=self.offer.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(reverse('accept-offer', args=[self.offer.id]))
        self.assertEqual(response.status_code, 409)
        self.ride.refresh_from_db()
        self.assertIsNone(self.ride.driver)

    def test_cannot_accept_offer_for_cancelled_ride(self):
        Ride.objects.filter(pk=self.ride.pk).update(status='cancelled')
        response = self.client.post(reverse('accept-offer', args=[self.offer.id]))
        self.assertEqual(response.status_code, 409)

    def test_cannot_accept_someone_elses_offer(self):
        other = self.make_driver(6.53, 3.36)
        self.client.force_authenticate(other)
        response = self.client.post(reverse('accept-offer', args=[self.offer.id]))
        self.assertEqual(response.status_code, 404)

    @patch('rides.views.find_driver_for_ride.delay')
    def test_decline_moves_on(self, mock_delay):
        response = self.client.post(reverse('decline-offer', args=[self.offer.id]))
        self.assertEqual(response.status_code, 200)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, 'declined')
        mock_delay.assert_called_once_with(self.ride.id)

    def test_rider_cancel_withdraws_offer(self):
        self.client.force_authenticate(self.rider)
        response = self.client.patch(reverse('cancel-ride', args=[self.ride.id]))
        self.assertEqual(response.status_code, 200)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, 'expired')
