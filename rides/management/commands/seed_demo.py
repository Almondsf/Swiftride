import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser
from tracking.models import DriverLocation

# Yaba, Lagos
CENTER = (6.5095, 3.3711)
DEMO_PASSWORD = 'demo12345'


class Command(BaseCommand):
    help = 'Create demo riders and online drivers scattered around a point, for trying the app locally.'

    def add_arguments(self, parser):
        parser.add_argument('--drivers', type=int, default=10)
        parser.add_argument('--riders', type=int, default=3)
        parser.add_argument('--lat', type=float, default=CENTER[0])
        parser.add_argument('--lng', type=float, default=CENTER[1])
        parser.add_argument('--spread-km', type=float, default=5, help='Drivers are placed within this distance')
        parser.add_argument('--force', action='store_true', help='Run even when DEBUG is off')

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            raise CommandError('Refusing to seed demo users with DEBUG off; pass --force if you really mean it.')

        spread_deg = options['spread_km'] / 111.0
        for i in range(1, options['drivers'] + 1):
            driver = self.demo_user(f'driver{i}@demo.swiftride', 'driver', f'0900000{i:04d}', f'Driver{i}')
            DriverLocation.objects.update_or_create(driver=driver, defaults={
                'latitude': round(options['lat'] + random.uniform(-spread_deg, spread_deg), 6),
                'longitude': round(options['lng'] + random.uniform(-spread_deg, spread_deg), 6),
                'is_online': True,
            })

        for i in range(1, options['riders'] + 1):
            self.demo_user(f'rider{i}@demo.swiftride', 'rider', f'0910000{i:04d}', f'Rider{i}')

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {options['drivers']} online drivers and {options['riders']} riders "
            f"around ({options['lat']}, {options['lng']})."
        ))
        self.stdout.write(f'Log in as driver1@demo.swiftride or rider1@demo.swiftride with password {DEMO_PASSWORD}')
        self.stdout.write('Driver locations go stale after 2 minutes; re-run this to bring them back online.')

    def demo_user(self, email, role, phone, first_name):
        user, created = CustomUser.objects.get_or_create(email=email, defaults={
            'role': role, 'phone_number': phone, 'first_name': first_name, 'last_name': 'Demo',
        })
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user
