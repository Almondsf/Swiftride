from django.urls import path
from .views import RideCreateView, RideListView, AvailableRidesView, AcceptRideView, StartRideView, CompleteRideView, CancelRideView, RideOfferListView, AcceptOfferView, DeclineOfferView, RateRideView, UserRatingView

urlpatterns = [
    path('request/', RideCreateView.as_view(), name='ride-request'),
    path('my-rides/', RideListView.as_view(), name='my-rides'),
    path('available/', AvailableRidesView.as_view(), name='available-rides'),
    path('<int:pk>/accept/', AcceptRideView.as_view(), name='accept-ride'),
    path('<int:pk>/start/', StartRideView.as_view(), name='start-ride'),
    path('<int:pk>/complete/', CompleteRideView.as_view(), name='complete-ride'),
    path('<int:pk>/cancel/', CancelRideView.as_view(), name='cancel-ride'),
    path('<int:pk>/rate/', RateRideView.as_view(), name='rate-ride'),
    path('users/<int:user_id>/rating/', UserRatingView.as_view(), name='user-rating'),
    path('offers/', RideOfferListView.as_view(), name='ride-offers'),
    path('offers/<int:pk>/accept/', AcceptOfferView.as_view(), name='accept-offer'),
    path('offers/<int:pk>/decline/', DeclineOfferView.as_view(), name='decline-offer'),
]