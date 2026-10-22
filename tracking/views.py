from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers, status
from rides.permissions import IsDriver
from .models import DriverLocation


class DriverLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverLocation
        fields = ['latitude', 'longitude', 'is_online', 'updated_at']
        read_only_fields = ['updated_at']


class DriverLocationView(APIView):
    """Drivers report where they are and whether they're taking rides."""
    permission_classes = [IsDriver]

    def get(self, request):
        location = DriverLocation.objects.filter(driver=request.user).first()
        if not location:
            return Response({'error': 'No location reported yet'}, status=status.HTTP_404_NOT_FOUND)
        return Response(DriverLocationSerializer(location).data)

    def post(self, request):
        location = DriverLocation.objects.filter(driver=request.user).first()
        serializer = DriverLocationSerializer(location, data=request.data, partial=location is not None)
        serializer.is_valid(raise_exception=True)
        serializer.save(driver=request.user)
        return Response(serializer.data)
