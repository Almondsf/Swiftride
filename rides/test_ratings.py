from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from tracking.models import DriverLocation
from .matching import offer_to_nearest_driver
from .models import Ride, Rating
from .ratings import rating_summary


class RatingFixtures:
    def setUp(self):
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.driver = CustomUser.objects.create_user(email='d@test.com', phone_number='0800000002', role='driver')
        self.phone = 10

    def make_ride(self, status='completed', driver=None, **kwargs):
        defaults = dict(
            rider=self.rider, driver=driver or self.driver, status=status,
            pickup_location='Yaba', dropoff_location='Ikeja',
            pickup_lat=Decimal('6.5095'), pickup_lng=Decimal('3.3711'),
            dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'),
        )
        defaults.update(kwargs)
        return Ride.objects.create(**defaults)

    def rate(self, ratee, score, count=1):
        for _ in range(count):
            ride = self.make_ride(driver=ratee)
            Rating.objects.create(ride=ride, rater=self.rider, ratee=ratee, score=score)


class RateRideTests(RatingFixtures, APITestCase):
    def test_rider_rates_driver(self):
        ride = self.make_ride()
        self.client.force_authenticate(self.rider)
        response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 5, 'comment': 'Smooth'}, format='json')
        self.assertEqual(response.status_code, 201)
        rating = Rating.objects.get(ride=ride)
        self.assertEqual((rating.rater, rating.ratee, rating.score), (self.rider, self.driver, 5))

    def test_driver_rates_rider(self):
        ride = self.make_ride()
        self.client.force_authenticate(self.driver)
        response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 4}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Rating.objects.get(ride=ride).ratee, self.rider)

    def test_cannot_rate_twice(self):
        ride = self.make_ride()
        self.client.force_authenticate(self.rider)
        self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 5}, format='json')
        response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 1}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Rating.objects.get(ride=ride).score, 5)

    def test_cannot_rate_unfinished_ride(self):
        ride = self.make_ride(status='in_progress')
        self.client.force_authenticate(self.rider)
        response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 5}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_outsider_cannot_rate(self):
        ride = self.make_ride()
        outsider = CustomUser.objects.create_user(email='o@test.com', phone_number='0800000009', role='rider')
        self.client.force_authenticate(outsider)
        response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': 1}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_score_must_be_1_to_5(self):
        ride = self.make_ride()
        self.client.force_authenticate(self.rider)
        for score in (0, 6):
            response = self.client.post(reverse('rate-ride', args=[ride.id]), {'score': score}, format='json')
            self.assertEqual(response.status_code, 400)

    def test_rating_summary_endpoint(self):
        self.rate(self.driver, 5, count=2)
        self.rate(self.driver, 4)
        self.client.force_authenticate(self.rider)
        response = self.client.get(reverse('user-rating', args=[self.driver.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'average': 4.67, 'count': 3})

    def test_summary_with_no_ratings(self):
        self.assertEqual(rating_summary(self.driver.id), {'average': None, 'count': 0})


class LowRatedDriverMatchingTests(RatingFixtures, TestCase):
    def make_online_driver(self, lat, lng):
        self.phone += 1
        driver = CustomUser.objects.create_user(
            email=f'd{self.phone}@test.com', phone_number=f'08000000{self.phone}', role='driver'
        )
        DriverLocation.objects.create(driver=driver, latitude=lat, longitude=lng, is_online=True)
        return driver

    def test_low_rated_driver_is_skipped(self):
        bad = self.make_online_driver(6.512, 3.372)       # nearest
        good = self.make_online_driver(6.53, 3.36)
        self.rate(bad, 2, count=5)
        ride = self.make_ride(status='requested', driver=None)
        ride.driver = None
        ride.save()
        self.assertEqual(offer_to_nearest_driver(ride).driver, good)

    def test_new_driver_with_few_bad_ratings_still_matched(self):
        newish = self.make_online_driver(6.512, 3.372)
        self.rate(newish, 1, count=2)  # below the minimum count, not judged yet
        ride = self.make_ride(status='requested')
        Ride.objects.filter(pk=ride.pk).update(driver=None)
        ride.refresh_from_db()
        self.assertEqual(offer_to_nearest_driver(ride).driver, newish)
