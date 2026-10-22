import math

from geopy.distance import geodesic

# roads aren't straight lines; a typical detour factor for city driving
ROAD_DISTANCE_FACTOR = 1.3
# rough average city speed including traffic
AVERAGE_SPEED_KMH = 25


def estimate_eta(from_lat, from_lng, to_lat, to_lng):
    distance_km = geodesic((from_lat, from_lng), (to_lat, to_lng)).km * ROAD_DISTANCE_FACTOR
    return {
        'distance_km': round(distance_km, 1),
        'eta_minutes': math.ceil(distance_km / AVERAGE_SPEED_KMH * 60),
    }


def eta_for_ride(ride, lat, lng):
    """ETA from the driver's position to wherever they're headed next on this ride."""
    if ride.status == 'accepted':
        heading_to, target = 'pickup', (ride.pickup_lat, ride.pickup_lng)
    elif ride.status == 'in_progress':
        heading_to, target = 'dropoff', (ride.dropoff_lat, ride.dropoff_lng)
    else:
        return {}

    if None in target:
        return {}
    return {'heading_to': heading_to, **estimate_eta(lat, lng, *target)}
