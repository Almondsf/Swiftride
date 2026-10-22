from django.db import models
from accounts.models import CustomUser

# Create your models here.

class DriverLocation(models.Model):
    driver = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='location')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_online = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_online', 'latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.driver.email} ({'online' if self.is_online else 'offline'})"
