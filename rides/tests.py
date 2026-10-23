from datetime import timedelta
from io import StringIO
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from tracking.models import DriverLocation
from .models import Ride


def make_user(email, role, phone):
    return CustomUser.objects.create_user(email=email, phone_number=phone, role=role)


class RideFlowTests(APITestCase):
    def setUp(self):
        self.rider = make_user('rider@test.com', 'rider', '0800000001')
        self.driver = make_user('driver@test.com', 'driver', '0800000002')
        self.other_driver = make_user('driver2@test.com', 'driver', '0800000003')

    def make_ride(self, **kwargs):
        defaults = dict(
            rider=self.rider, pickup_location='Yaba', dropoff_location='Ikeja',
            pickup_lat=Decimal('6.5095'), pickup_lng=Decimal('3.3711'),
            dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'),
        )
        defaults.update(kwargs)
        return Ride.objects.create(**defaults)

    @patch('rides.views.find_driver_for_ride.delay')
    def test_request_ride_requires_coordinates(self, mock_delay):
        self.client.force_authenticate(self.rider)
        response = self.client.post(reverse('ride-request'), {
            'pickup_location': 'Yaba', 'dropoff_location': 'Ikeja',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        mock_delay.assert_not_called()

    @patch('rides.views.find_driver_for_ride.delay')
    def test_rider_cannot_mark_ride_paid(self, mock_delay):
        self.client.force_authenticate(self.rider)
        response = self.client.post(reverse('ride-request'), {
            'pickup_location': 'Yaba', 'dropoff_location': 'Ikeja',
            'pickup_lat': '6.5095', 'pickup_lng': '3.3711',
            'dropoff_lat': '6.6018', 'dropoff_lng': '3.3515',
            'is_paid': True, 'payment_reference': 'fake',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        ride = Ride.objects.get(id=response.data['id'])
        self.assertFalse(ride.is_paid)
        self.assertIsNone(ride.payment_reference)
        mock_delay.assert_called_once_with(ride.id)

    def test_accept_ride(self):
        ride = self.make_ride()
        self.client.force_authenticate(self.driver)
        response = self.client.patch(reverse('accept-ride', args=[ride.id]))
        self.assertEqual(response.status_code, 200)
        ride.refresh_from_db()
        self.assertEqual(ride.driver, self.driver)
        self.assertEqual(ride.status, 'accepted')

    def test_second_driver_cannot_take_accepted_ride(self):
        ride = self.make_ride(driver=self.driver, status='accepted')
        self.client.force_authenticate(self.other_driver)
        response = self.client.patch(reverse('accept-ride', args=[ride.id]))
        self.assertEqual(response.status_code, 409)
        ride.refresh_from_db()
        self.assertEqual(ride.driver, self.driver)

    def test_driver_with_active_ride_cannot_accept_another(self):
        self.make_ride(driver=self.driver, status='in_progress')
        ride = self.make_ride()
        self.client.force_authenticate(self.driver)
        response = self.client.patch(reverse('accept-ride', args=[ride.id]))
        self.assertEqual(response.status_code, 409)

    def test_fare_is_charged_from_trip_start_not_request_time(self):
        ride = self.make_ride(driver=self.driver, status='in_progress')
        # rider waited an hour for pickup, trip itself took 10 minutes
        Ride.objects.filter(id=ride.id).update(
            created_at=timezone.now() - timedelta(hours=1),
            started_at=timezone.now() - timedelta(minutes=10),
        )
        self.client.force_authenticate(self.driver)
        response = self.client.patch(reverse('complete-ride', args=[ride.id]))
        self.assertEqual(response.status_code, 200)
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'completed')
        self.assertIsNotNone(ride.completed_at)
        # ~10.3km and ~10 min: 500 + ~1030 + ~200. An hour of waiting would add 1000+.
        self.assertLess(ride.fare, Decimal('2000'))

    def test_start_sets_started_at(self):
        ride = self.make_ride(driver=self.driver, status='accepted')
        self.client.force_authenticate(self.driver)
        response = self.client.patch(reverse('start-ride', args=[ride.id]))
        self.assertEqual(response.status_code, 200)
        ride.refresh_from_db()
        self.assertEqual(ride.status, 'in_progress')
        self.assertIsNotNone(ride.started_at)


class FareEstimateTests(APITestCase):
    def setUp(self):
        # throttle counters and cached surge live in the cache, which outlives each test
        cache.clear()

    def test_client_cannot_set_surge(self):
        rider = make_user('rider@test.com', 'rider', '0800000001')
        self.client.force_authenticate(rider)
        url = reverse('fare-estimate')
        body = {'pickup': [6.5095, 3.3711], 'dropoff': [6.6018, 3.3515], 'duration_minutes': 10}
        normal = self.client.post(url, body, format='json').data['estimated_fare']
        surged = self.client.post(url, {**body, 'surge_multiplier': 0.1}, format='json').data['estimated_fare']
        self.assertEqual(normal, surged)


class SeedDemoCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_seeds_online_drivers_and_riders_idempotently(self):
        call_command('seed_demo', drivers=4, riders=2, stdout=StringIO())
        call_command('seed_demo', drivers=4, riders=2, stdout=StringIO())
        self.assertEqual(CustomUser.objects.filter(role='driver').count(), 4)
        self.assertEqual(CustomUser.objects.filter(role='rider').count(), 2)
        self.assertEqual(DriverLocation.objects.filter(is_online=True).count(), 4)
        self.assertTrue(CustomUser.objects.get(email='rider1@demo.swiftride').check_password('demo12345'))

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())
