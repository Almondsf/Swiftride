from .models import Ride, RideOffer
from rest_framework.serializers import ModelSerializer

class RideSerializer(ModelSerializer):
    class Meta:
        model = Ride
        fields = ['id', 'rider', 'driver', 'status', 'pickup_location', 'dropoff_location', 'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'fare', 'surge_multiplier', 'payment_reference', 'is_paid', 'created_at', 'updated_at', 'started_at', 'completed_at']
        read_only_fields = ['id', 'rider', 'driver', 'status', 'fare', 'surge_multiplier', 'payment_reference', 'is_paid', 'created_at', 'updated_at', 'started_at', 'completed_at']
        # coordinates are needed for driver matching and fare calculation
        extra_kwargs = {
            'pickup_lat': {'required': True, 'allow_null': False},
            'pickup_lng': {'required': True, 'allow_null': False},
            'dropoff_lat': {'required': True, 'allow_null': False},
            'dropoff_lng': {'required': True, 'allow_null': False},
        }


class RideOfferSerializer(ModelSerializer):
    ride = RideSerializer(read_only=True)

    class Meta:
        model = RideOffer
        fields = ['id', 'ride', 'status', 'created_at', 'expires_at']
        read_only_fields = fields
