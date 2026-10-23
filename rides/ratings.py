from django.db.models import Avg, Count

from .models import Rating

# drivers averaging below this, once they have enough ratings to judge, stop getting offers
LOW_RATING_THRESHOLD = 3.5
MIN_RATINGS_FOR_CUTOFF = 5


def rating_summary(user_id):
    result = Rating.objects.filter(ratee_id=user_id).aggregate(average=Avg('score'), count=Count('id'))
    average = result['average']
    return {
        'average': round(average, 2) if average is not None else None,
        'count': result['count'],
    }


def low_rated_driver_ids():
    return Rating.objects.values('ratee_id').annotate(
        average=Avg('score'), count=Count('id')
    ).filter(
        count__gte=MIN_RATINGS_FOR_CUTOFF, average__lt=LOW_RATING_THRESHOLD
    ).values('ratee_id')
