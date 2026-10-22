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
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Ride {self.id} ({self.status})"


class RideOffer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='offers')
    driver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='ride_offers')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            # a ride is never offered to the same driver twice
            models.UniqueConstraint(fields=['ride', 'driver'], name='unique_offer_per_driver'),
        ]

    def __str__(self):
        return f"Offer {self.id}: ride {self.ride_id} -> {self.driver_id} ({self.status})"
