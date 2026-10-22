from decimal import Decimal
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import CustomUser
from rides.models import Ride, RideOffer
from rides.tasks import find_driver_for_ride
from .consumers import LocationConsumer
from .models import DriverLocation


class DriverLocationViewTests(APITestCase):
    def setUp(self):
        self.driver = CustomUser.objects.create_user(email='d@test.com', phone_number='0800000002', role='driver')
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.url = reverse('driver-location')

    def test_driver_goes_online(self):
        self.client.force_authenticate(self.driver)
        response = self.client.post(self.url, {'latitude': '6.5', 'longitude': '3.37', 'is_online': True}, format='json')
        self.assertEqual(response.status_code, 200)
        location = DriverLocation.objects.get(driver=self.driver)
        self.assertTrue(location.is_online)

    def test_driver_can_go_offline_without_resending_location(self):
        DriverLocation.objects.create(driver=self.driver, latitude=6.5, longitude=3.37, is_online=True)
        self.client.force_authenticate(self.driver)
        response = self.client.post(self.url, {'is_online': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DriverLocation.objects.get(driver=self.driver).is_online)

    def test_first_report_needs_coordinates(self):
        self.client.force_authenticate(self.driver)
        response = self.client.post(self.url, {'is_online': True}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_riders_cannot_report_location(self):
        self.client.force_authenticate(self.rider)
        response = self.client.post(self.url, {'latitude': '6.5', 'longitude': '3.37'}, format='json')
        self.assertEqual(response.status_code, 403)


class LocationConsumerTests(TransactionTestCase):
    def setUp(self):
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.driver = CustomUser.objects.create_user(email='d@test.com', phone_number='0800000002', role='driver')
        self.stranger = CustomUser.objects.create_user(email='s@test.com', phone_number='0800000003', role='rider')
        self.ride = Ride.objects.create(
            rider=self.rider, driver=self.driver, status='accepted',
            pickup_location='A', dropoff_location='B',
        )

    def communicator(self, user):
        communicator = WebsocketCommunicator(LocationConsumer.as_asgi(), f'/ws/tracking/{self.ride.id}/')
        communicator.scope['user'] = user
        communicator.scope['url_route'] = {'kwargs': {'ride_id': str(self.ride.id)}}
        return communicator

    def test_driver_location_is_broadcast_and_saved(self):
        async def run():
            driver_ws = self.communicator(self.driver)
            rider_ws = self.communicator(self.rider)
            self.assertTrue((await driver_ws.connect(timeout=5))[0])
            self.assertTrue((await rider_ws.connect(timeout=5))[0])
            await driver_ws.send_json_to({'latitude': 6.51, 'longitude': 3.37})
            message = await rider_ws.receive_json_from(timeout=5)
            self.assertEqual(message, {'latitude': 6.51, 'longitude': 3.37})
            await driver_ws.disconnect()
            await rider_ws.disconnect()

        async_to_sync(run)()
        location = DriverLocation.objects.get(driver=self.driver)
        self.assertEqual(location.latitude, Decimal('6.51'))

    def test_stranger_is_rejected(self):
        async def run():
            ws = self.communicator(self.stranger)
            connected, _ = await ws.connect(timeout=5)
            self.assertFalse(connected)

        async_to_sync(run)()


class NotificationTests(TransactionTestCase):
    """End to end through the real ASGI app, authenticating with a JWT."""

    def setUp(self):
        self.rider = CustomUser.objects.create_user(email='r@test.com', phone_number='0800000001', role='rider')
        self.driver = CustomUser.objects.create_user(email='d@test.com', phone_number='0800000002', role='driver')
        DriverLocation.objects.create(driver=self.driver, latitude=6.512, longitude=3.372, is_online=True)
        self.ride = Ride.objects.create(
            rider=self.rider, pickup_location='Yaba', dropoff_location='Ikeja',
            pickup_lat=Decimal('6.5095'), pickup_lng=Decimal('3.3711'),
            dropoff_lat=Decimal('6.6018'), dropoff_lng=Decimal('3.3515'),
        )

    def connect(self, token):
        from swiftride.asgi import application
        return WebsocketCommunicator(application, f'/ws/notifications/?token={token}')

    def test_bad_token_rejected(self):
        async def run():
            connected, _ = await self.connect('not-a-jwt').connect(timeout=5)
            self.assertFalse(connected)

        async_to_sync(run)()

    @patch('rides.tasks.expire_offer.apply_async')
    def test_driver_gets_offer_and_rider_gets_acceptance(self, mock_expire):
        driver_token = str(AccessToken.for_user(self.driver))
        rider_token = str(AccessToken.for_user(self.rider))

        def accept_offer():
            offer = RideOffer.objects.get(ride=self.ride)
            client = APIClient()
            client.force_authenticate(self.driver)
            return client.post(reverse('accept-offer', args=[offer.id])).status_code

        async def run():
            driver_ws = self.connect(driver_token)
            rider_ws = self.connect(rider_token)
            self.assertTrue((await driver_ws.connect(timeout=5))[0])
            self.assertTrue((await rider_ws.connect(timeout=5))[0])

            await database_sync_to_async(find_driver_for_ride)(self.ride.id)
            offer_message = await driver_ws.receive_json_from(timeout=5)
            self.assertEqual(offer_message['event'], 'ride.offer')
            self.assertEqual(offer_message['data']['ride_id'], self.ride.id)

            self.assertEqual(await database_sync_to_async(accept_offer)(), 200)
            for ws in (rider_ws, driver_ws):
                status_message = await ws.receive_json_from(timeout=5)
                self.assertEqual(status_message['event'], 'ride.status')
                self.assertEqual(status_message['data']['status'], 'accepted')
                self.assertEqual(status_message['data']['driver_id'], self.driver.id)

            await driver_ws.disconnect()
            await rider_ws.disconnect()

        async_to_sync(run)()
