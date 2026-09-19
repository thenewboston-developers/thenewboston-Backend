from django.contrib.auth import get_user_model
from django.db.models import Prefetch

from ..models import Comment

User = get_user_model()


def get_comment_read_queryset():
    return Comment.objects.select_related('owner__connect_five_stats', 'price_currency').prefetch_related(
        Prefetch('mentioned_users', queryset=User.objects.select_related('connect_five_stats'))
    )
