from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from rides.models import Ride
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
            self.assertTrue((await driver_ws.connect())[0])
            self.assertTrue((await rider_ws.connect())[0])
            await driver_ws.send_json_to({'latitude': 6.51, 'longitude': 3.37})
            message = await rider_ws.receive_json_from()
            self.assertEqual(message, {'latitude': 6.51, 'longitude': 3.37})
            await driver_ws.disconnect()
            await rider_ws.disconnect()

        async_to_sync(run)()
        location = DriverLocation.objects.get(driver=self.driver)
        self.assertEqual(location.latitude, Decimal('6.51'))

    def test_stranger_is_rejected(self):
        async def run():
            ws = self.communicator(self.stranger)
            connected, _ = await ws.connect()
            self.assertFalse(connected)

        async_to_sync(run)()
