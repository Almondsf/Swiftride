from django.urls import path
from .views import DriverLocationView

urlpatterns = [
    path('driver/location/', DriverLocationView.as_view(), name='driver-location'),
]
