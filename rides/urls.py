from django.urls import path
from .views import RideCreateView, RideListView, AvailableRidesView, AcceptRideView, StartRideView, CompleteRideView, CancelRideView  

urlpatterns = [
    path('request/', RideCreateView.as_view(), name='ride-request'),
    path('my-rides/', RideListView.as_view(), name='my-rides'),
    path('available/', AvailableRidesView.as_view(), name='available-rides'),
    path('<int:pk>/accept/', AcceptRideView.as_view(), name='accept-ride'),
    path('<int:pk>/start/', StartRideView.as_view(), name='start-ride'),
    path('<int:pk>/complete/', CompleteRideView.as_view(), name='complete-ride'),
    path('<int:pk>/cancel/', CancelRideView.as_view(), name='cancel-ride'),
]