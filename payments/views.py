from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rides.models import Ride
from .paystack import inititalize_payment, verify_payment
from rest_framework.throttling import UserRateThrottle
import hmac
import hashlib
from django.conf import settings


class PaymentRateThrottle(UserRateThrottle):
    rate = '5/minute'
class InitializePaymentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentRateThrottle]

    def post(self, request):
        ride_id = request.data.get('ride_id')
        ride = get_object_or_404(Ride, id=ride_id, rider=request.user)

        if ride.status != 'completed':
            return Response({'error': 'Ride not completed'}, status=400)
        if ride.is_paid:
            return Response({'error': 'Ride has already been paid for'}, status=400)

        response = inititalize_payment(request.user.email, ride.fare)

        ride.payment_reference = response['data']['reference']
        ride.save()
        return Response({
            'authorization_url': response['data']['authorization_url'],
            'reference': response['data']['reference']
        })


class PaymentWebhookView(APIView):
    # Paystack calls this directly, so no JWT auth or throttling;
    # requests are authenticated by the signature instead.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        paystack_signature = request.headers.get('x-paystack-signature', '')
        computed_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(paystack_signature, computed_signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        if request.data.get('event') != 'charge.success':
            return Response({'status': 'ignored'})

        reference = request.data.get('data', {}).get('reference')
        ride = get_object_or_404(Ride, payment_reference=reference)

        # don't trust the webhook body alone, confirm with Paystack
        response = verify_payment(reference)
        data = response.get('data') or {}
        expected_amount = int(ride.fare * 100)

        if data.get('status') == 'success' and data.get('amount') == expected_amount:
            ride.is_paid = True
            ride.save()

        return Response({'status': 'ok'})
