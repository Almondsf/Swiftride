from decimal import Decimal

from django.test import SimpleTestCase

from .eta import eta_for_ride
from .models import Ride

PICKUP = dict(pickup_lat=Decimal('6.5095'), pickup_lng=Decimal('3.3711'))
DROPOFF = dict(dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'))


class EtaForRideTests(SimpleTestCase):
    def test_heads_to_pickup_when_accepted(self):
        eta = eta_for_ride(Ride(status='accepted', **PICKUP, **DROPOFF), 6.5295, 3.3711)
        self.assertEqual(eta['heading_to'], 'pickup')
        self.assertEqual(eta['eta_minutes'], 7)

    def test_heads_to_dropoff_when_in_progress(self):
        eta = eta_for_ride(Ride(status='in_progress', **PICKUP, **DROPOFF), 6.5095, 3.3711)
        self.assertEqual(eta['heading_to'], 'dropoff')
        # ~10.3km straight line, ~13.4km by road at 25km/h
        self.assertEqual(eta['eta_minutes'], 33)

    def test_nothing_for_other_statuses_or_missing_coordinates(self):
        self.assertEqual(eta_for_ride(Ride(status='completed', **PICKUP, **DROPOFF), 6.5, 3.3), {})
        self.assertEqual(eta_for_ride(Ride(status='accepted'), 6.5, 3.3), {})
