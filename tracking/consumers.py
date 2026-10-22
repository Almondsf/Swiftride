import json
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from rides.models import Ride
from rides.notifications import user_group
from channels.db import database_sync_to_async
from .models import DriverLocation


@database_sync_to_async
def save_driver_location(driver, latitude, longitude):
    DriverLocation.objects.update_or_create(
        driver=driver,
        defaults={'latitude': latitude, 'longitude': longitude},
    )

class LocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.ride_id = self.scope['url_route']['kwargs']['ride_id']
        self.room_group_name = f'ride_{self.ride_id}'
        
        user = self.scope['user']
        
        # reject anonymous users
        if user.is_anonymous:
            await self.close()
            return
        
        # reject users not part of this ride
        try:
            ride = await database_sync_to_async(Ride.objects.get)(
                id=self.ride_id
            )
            # compare ids: touching ride.rider/ride.driver would hit the DB from async code
            if user.id not in (ride.rider_id, ride.driver_id):
                await self.close()
                return
            self.is_driver = user.id == ride.driver_id
        except Ride.DoesNotExist:
            await self.close()
            return
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        latitude = data['latitude']
        longitude = data['longitude']
        
        # the driver's live position also keeps their matching location fresh
        if self.is_driver:
            await save_driver_location(self.scope['user'], latitude, longitude)
        
        # broadcast to everyone in the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'location_update',
                'latitude': latitude,
                'longitude': longitude,
            }
        )
        
    async def location_update(self, event):
        await self.send(text_data=json.dumps({
            'latitude': event['latitude'],
            'longitude': event['longitude'],
        }))

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Per-user stream of ride events (offers, status changes)."""

    async def connect(self):
        user = self.scope['user']
        if user.is_anonymous:
            await self.close()
            return
        
        self.group_name = user_group(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def notify(self, event):
        await self.send_json({'event': event['event'], 'data': event['data']})
