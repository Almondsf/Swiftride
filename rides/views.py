from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import Ride
from .serializers import RideSerializer
from .permissions import IsRider, IsDriver
from pricing.calculator import calculate_fare
from django.utils import timezone
from geopy.distance import geodesic
from .tasks import find_driver_for_ride

class RideCreateView(generics.CreateAPIView):
    queryset = Ride.objects.all()
    serializer_class = RideSerializer
    permission_classes = [IsRider]
    
    def perform_create(self, serializer):
        ride = serializer.save(rider=self.request.user)
        find_driver_for_ride.delay(ride.id)
    
    
class RideListView(generics.ListAPIView):
    queryset = Ride.objects.all()
    serializer_class = RideSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        return Ride.objects.filter(rider=user) | Ride.objects.filter(driver=user)
    
class AvailableRidesView(generics.ListAPIView):
    queryset = Ride.objects.filter(status='requested')
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    

class AcceptRideView(generics.UpdateAPIView):
    queryset = Ride.objects.filter(status='requested')
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    
    
    def perform_update(self, serializer):
        serializer.save(driver=self.request.user, status='accepted')

class StartRideView(generics.UpdateAPIView):
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    
    def get_queryset(self):
       return Ride.objects.filter(status='accepted', driver=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(status='in_progress')   

class CompleteRideView(generics.UpdateAPIView):
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    
    def get_queryset(self):
       return Ride.objects.filter(status='in_progress', driver=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(status='completed')

class CancelRideView(generics.UpdateAPIView):
    serializer_class = RideSerializer
    permission_classes = [IsRider]
    
    def get_queryset(self):
        return Ride.objects.filter(status__in=['requested', 'accepted'], rider=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(status='cancelled')
        
class CompleteRideView(generics.UpdateAPIView):
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    
    def get_queryset(self):
       return Ride.objects.filter(status='in_progress', driver=self.request.user)
    
    def perform_update(self, serializer):
        ride = self.get_object()
        
        duration = timezone.now() - ride.created_at
        duration_minutes = duration.total_seconds() / 60
        distance_km = geodesic(
            (ride.pickup_lat, ride.pickup_lng),
            (ride.dropoff_lat, ride.dropoff_lng)
        ).km
        fare =  calculate_fare(distance_km, duration_minutes)
        serializer.save(status='completed', fare=fare)