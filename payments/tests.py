import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from rides.models import Ride


def sign(body):
    return hmac.new(settings.PAYSTACK_SECRET_KEY.encode('utf-8'), body, hashlib.sha512).hexdigest()


class PaymentWebhookTests(APITestCase):
    def setUp(self):
        self.rider = CustomUser.objects.create_user(
            email='rider@test.com', password='pass12345', phone_number='0800000001', role='rider'
        )
        self.ride = Ride.objects.create(
            rider=self.rider, pickup_location='A', dropoff_location='B',
            status='completed', fare=Decimal('1500.00'), payment_reference='ref_123',
        )
        self.url = reverse('payment-webhook')

    def post_event(self, payload, signature=None):
        body = json.dumps(payload).encode('utf-8')
        return self.client.post(
            self.url, data=body, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature if signature is not None else sign(body),
        )

    def charge_success(self):
        return {'event': 'charge.success', 'data': {'reference': 'ref_123'}}

    @patch('payments.views.verify_payment')
    def test_valid_webhook_marks_ride_paid(self, mock_verify):
        mock_verify.return_value = {'data': {'status': 'success', 'amount': 150000}}
        response = self.post_event(self.charge_success())
        self.assertEqual(response.status_code, 200)
        self.ride.refresh_from_db()
        self.assertTrue(self.ride.is_paid)

    @patch('payments.views.verify_payment')
    def test_invalid_signature_rejected(self, mock_verify):
        response = self.post_event(self.charge_success(), signature='bad')
        self.assertEqual(response.status_code, 400)
        mock_verify.assert_not_called()
        self.ride.refresh_from_db()
        self.assertFalse(self.ride.is_paid)

    @patch('payments.views.verify_payment')
    def test_missing_signature_rejected(self, mock_verify):
        body = json.dumps(self.charge_success()).encode('utf-8')
        response = self.client.post(self.url, data=body, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        mock_verify.assert_not_called()

    @patch('payments.views.verify_payment')
    def test_amount_mismatch_not_marked_paid(self, mock_verify):
        mock_verify.return_value = {'data': {'status': 'success', 'amount': 100}}
        self.post_event(self.charge_success())
        self.ride.refresh_from_db()
        self.assertFalse(self.ride.is_paid)

    @patch('payments.views.verify_payment')
    def test_other_events_ignored(self, mock_verify):
        response = self.post_event({'event': 'transfer.success', 'data': {}})
        self.assertEqual(response.status_code, 200)
        mock_verify.assert_not_called()


class InitializePaymentTests(APITestCase):
    def setUp(self):
        self.rider = CustomUser.objects.create_user(
            email='rider@test.com', password='pass12345', phone_number='0800000001', role='rider'
        )
        self.ride = Ride.objects.create(
            rider=self.rider, pickup_location='A', dropoff_location='B',
            status='completed', fare=Decimal('1500.00'),
        )
        self.client.force_authenticate(self.rider)

    @patch('payments.views.inititalize_payment')
    def test_initialize_works_without_signature(self, mock_init):
        mock_init.return_value = {'data': {'reference': 'ref_abc', 'authorization_url': 'https://pay'}}
        response = self.client.post(reverse('initialize-payment'), {'ride_id': self.ride.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.ride.refresh_from_db()
        self.assertEqual(self.ride.payment_reference, 'ref_abc')
