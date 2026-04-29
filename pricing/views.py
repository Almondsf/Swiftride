from geopy.distance import geodesic
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .calculator import calculate_fare
from rest_framework.throttling import UserRateThrottle
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator


class FareEstimateRateThrottle(UserRateThrottle):
    rate = '10/minute'
    
@method_decorator(cache_page(60 * 15), name='dispatch')
class FareEstimateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [FareEstimateRateThrottle]
    def post(self, request):
        try:
            pickup = request.data.get('pickup')
            dropoff = request.data.get('dropoff')
            duration_minutes = request.data.get('duration_minutes', 0)
            surge_multiplier = request.data.get('surge_multiplier', 1.0)

            if not pickup or not dropoff:
                return Response({'error': 'Pickup and dropoff locations are required.'}, status=status.HTTP_400_BAD_REQUEST)

            distance_km = geodesic(pickup, dropoff).kilometers
            fare = calculate_fare(distance_km, duration_minutes, surge_multiplier)

            return Response({'estimated_fare': fare}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)