from celery import shared_task

from .services import sweep_tournaments


@shared_task(name='tasks.sweep_tribes')
def sweep_tribes():
    return sweep_tournaments()
