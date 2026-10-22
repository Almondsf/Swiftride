from django.urls import path
from  .views import FareEstimateView, SurgeView

urlpatterns = [
    path('fare-estimate/', FareEstimateView.as_view(), name='fare-estimate'),
    path('surge/', SurgeView.as_view(), name='surge'),
]