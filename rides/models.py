from django.db import models
from accounts.models import CustomUser

# Create your models here.

class Ride(models.Model):
    STATUS_CHOICES = [
    ('requested', 'Requested'),
    ('accepted', 'Accepted'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

    rider = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='rides')
    driver = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='drives')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fare = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    payment_reference = models.CharField(max_length=100, null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)