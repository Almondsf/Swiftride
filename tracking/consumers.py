import json
from channels.generic.websocket import AsyncWebsocketConsumer
from rides.models import Ride
from channels.db import database_sync_to_async

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
            if user != ride.rider and user != ride.driver:
                await self.close()
                return
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