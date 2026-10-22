from geopy.distance import geodesic
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .calculator import calculate_fare
from .surge import current_surge
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

            if not pickup or not dropoff:
                return Response({'error': 'Pickup and dropoff locations are required.'}, status=status.HTTP_400_BAD_REQUEST)

            distance_km = geodesic(pickup, dropoff).kilometers
            surge = current_surge(*pickup)
            fare = calculate_fare(distance_km, duration_minutes, float(surge))

            return Response({'estimated_fare': fare, 'surge_multiplier': surge}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SurgeView(APIView):
    """Current surge at a location, e.g. for a banner before the rider books."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            lat = float(request.query_params['lat'])
            lng = float(request.query_params['lng'])
        except (KeyError, ValueError):
            return Response({'error': 'lat and lng query parameters are required.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'surge_multiplier': current_surge(lat, lng)})
