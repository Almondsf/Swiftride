from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
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
    
    def update(self, request, *args, **kwargs):
        if Ride.objects.filter(driver=request.user, status__in=['accepted', 'in_progress']).exists():
            return Response({'error': 'You already have an active ride'}, status=status.HTTP_409_CONFLICT)
        
        # conditional update so two drivers can't both grab the same ride
        updated = Ride.objects.filter(pk=kwargs['pk'], status='requested').update(
            driver=request.user, status='accepted', updated_at=timezone.now()
        )
        if not updated:
            return Response({'error': 'Ride is no longer available'}, status=status.HTTP_409_CONFLICT)
        
        ride = Ride.objects.get(pk=kwargs['pk'])
        return Response(self.get_serializer(ride).data)

class StartRideView(generics.UpdateAPIView):
    serializer_class = RideSerializer
    permission_classes = [IsDriver]
    
    def get_queryset(self):
       return Ride.objects.filter(status='accepted', driver=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(status='in_progress', started_at=timezone.now())

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
        
        completed_at = timezone.now()
        duration = completed_at - (ride.started_at or ride.created_at)
        duration_minutes = duration.total_seconds() / 60
        distance_km = geodesic(
            (ride.pickup_lat, ride.pickup_lng),
            (ride.dropoff_lat, ride.dropoff_lng)
        ).km
        fare =  calculate_fare(distance_km, duration_minutes)
        serializer.save(status='completed', fare=fare, completed_at=completed_at)