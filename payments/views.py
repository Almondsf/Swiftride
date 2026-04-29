from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
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
        paystack_signature = request.headers.get('x-paystack-signature')
        computed_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(paystack_signature, computed_signature):
            return Response({'error': 'Invalid signature'}, status=400)
        
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
    
    def post(self, request):
        reference = request.data.get('reference')
        response = verify_payment(reference)
        
        if response['data']['status'] == 'success':
            ride = get_object_or_404(Ride, payment_reference=reference)
            ride.is_paid = True
            ride.save()
    
        return Response({'status': 'ok'})