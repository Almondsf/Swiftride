
def calculate_fare(distance_km, duration_minutes, surge_multiplier=1.0):
    base_fare = 500
    per_km_rate = 100
    per_minute_rate = 20

    fare = (base_fare + (per_km_rate * distance_km) + (per_minute_rate * duration_minutes)) * surge_multiplier
    return round(fare, 2)