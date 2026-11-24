from django.utils import timezone

from thenewboston.project.celery import app

from .models import GuestGameSession


@app.task(name='tasks.delete_expired_guest_games')
def delete_expired_guest_games():
    # Bounded batches keep anonymous match data from accumulating indefinitely.
    sessions = list(GuestGameSession.objects.filter(expires_at__lte=timezone.now()).values_list('pk', flat=True)[:500])
    GuestGameSession.objects.filter(pk__in=sessions).delete()
