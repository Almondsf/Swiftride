from .models import Ride
from rest_framework.serializers import ModelSerializer

class RideSerializer(ModelSerializer):
    class Meta:
        model = Ride
        fields = ['id', 'rider', 'driver', 'status', 'pickup_location', 'dropoff_location', 'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'fare', 'payment_reference', 'is_paid', 'created_at', 'updated_at']
        read_only_fields = ['id', 'rider', 'driver', 'status', 'fare', 'created_at', 'updated_at']