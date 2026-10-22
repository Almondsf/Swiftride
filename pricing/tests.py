from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from rides.models import Ride
from tracking.models import DriverLocation
from .surge import calculate_surge, current_surge

# Yaba, Lagos
LAT, LNG = 6.5095, 3.3711


class CalculateSurgeTests(TestCase):
    def test_no_surge_when_supply_keeps_up(self):
        self.assertEqual(calculate_surge(demand=3, supply=5), Decimal('1.0'))
        self.assertEqual(calculate_surge(demand=0, supply=0), Decimal('1.0'))

    def test_surge_scales_with_imbalance(self):
        self.assertEqual(calculate_surge(demand=6, supply=3), Decimal('1.5'))
        self.assertEqual(calculate_surge(demand=9, supply=3), Decimal('2.0'))

    def test_no_drivers_counts_as_one(self):
        self.assertEqual(calculate_surge(demand=2, supply=0), Decimal('1.5'))

    def test_capped(self):
        self.assertEqual(calculate_surge(demand=100, supply=1), Decimal('3.0'))


class SurgeFixtures:
    def setUp(self):
        cache.clear()
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.phone = 10

    def add_driver(self, lat=LAT + 0.001, lng=LNG):
        self.phone += 1
        driver = CustomUser.objects.create_user(
            email=f'd{self.phone}@test.com', phone_number=f'08000000{self.phone}', role='driver'
        )
        DriverLocation.objects.create(driver=driver, latitude=lat, longitude=lng, is_online=True)

    def add_requests(self, count, lat=LAT, lng=LNG):
        for _ in range(count):
            Ride.objects.create(
                rider=self.rider, pickup_location='Yaba', dropoff_location='Ikeja',
                pickup_lat=Decimal(str(lat)), pickup_lng=Decimal(str(lng)),
                dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'),
            )


class CurrentSurgeTests(SurgeFixtures, TestCase):
    def test_surge_from_nearby_demand_and_supply(self):
        self.add_driver()
        self.add_driver()
        self.add_requests(6)
        self.assertEqual(current_surge(LAT, LNG), Decimal('2.0'))

    def test_far_away_and_old_requests_dont_count(self):
        self.add_driver()
        self.add_requests(5, lat=6.70)  # ~21km north
        self.add_requests(5)
        Ride.objects.filter(pickup_lat=Decimal(str(LAT))).update(created_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(current_surge(LAT, LNG), Decimal('1.0'))

    def test_cached_per_cell(self):
        self.add_requests(5)
        self.assertEqual(current_surge(LAT, LNG), Decimal('3.0'))
        # drivers come online, but the cached value holds for the cell until it expires
        for _ in range(5):
            self.add_driver()
        self.assertEqual(current_surge(LAT + 0.001, LNG), Decimal('3.0'))
        cache.clear()
        self.assertEqual(current_surge(LAT, LNG), Decimal('1.0'))


class SurgeEndpointTests(SurgeFixtures, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.rider)

    def test_surge_endpoint(self):
        self.add_requests(3)
        response = self.client.get(reverse('surge'), {'lat': LAT, 'lng': LNG})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.data['surge_multiplier'])), Decimal('2.0'))

    def test_surge_endpoint_requires_coordinates(self):
        response = self.client.get(reverse('surge'), {'lat': LAT})
        self.assertEqual(response.status_code, 400)

    def test_fare_estimate_includes_surge(self):
        body = {'pickup': [LAT, LNG], 'dropoff': [6.6018, 3.3515], 'duration_minutes': 10}
        normal = self.client.post(reverse('fare-estimate'), body, format='json').data
        self.assertEqual(Decimal(str(normal['surge_multiplier'])), Decimal('1.0'))

        cache.clear()
        self.add_requests(3)
        surged = self.client.post(reverse('fare-estimate'), body, format='json').data
        self.assertEqual(Decimal(str(surged['surge_multiplier'])), Decimal('2.0'))
        self.assertAlmostEqual(surged['estimated_fare'], normal['estimated_fare'] * 2, places=1)

    @patch('rides.views.find_driver_for_ride.delay')
    def test_ride_locks_in_surge_and_is_charged_it(self, mock_delay):
        self.add_requests(3)
        response = self.client.post(reverse('ride-request'), {
            'pickup_location': 'Yaba', 'dropoff_location': 'Ikeja',
            'pickup_lat': str(LAT), 'pickup_lng': str(LNG),
            'dropoff_lat': '6.6018', 'dropoff_lng': '3.3515',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        ride = Ride.objects.get(id=response.data['id'])
        self.assertEqual(ride.surge_multiplier, Decimal('2.0'))

        # surge has gone away by the time the trip ends; rider still pays what they were quoted
        cache.clear()
        Ride.objects.exclude(id=ride.id).delete()
        driver = CustomUser.objects.create_user(email='drv@test.com', phone_number='0800000099', role='driver')
        Ride.objects.filter(id=ride.id).update(driver=driver, status='in_progress', started_at=timezone.now())
        self.client.force_authenticate(driver)
        self.client.patch(reverse('complete-ride', args=[ride.id]))
        ride.refresh_from_db()
        # ~10.3km, ~0 min: (500 + ~1030) * 2.0
        self.assertGreater(ride.fare, Decimal('3000'))
