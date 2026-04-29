from django.urls import path
from .views import InitializePaymentView, PaymentWebhookView

urlpatterns = [
    path('initialize/', InitializePaymentView.as_view(), name='initialize-payment'),
    path('webhook/', PaymentWebhookView.as_view(), name='payment-webhook'),
]