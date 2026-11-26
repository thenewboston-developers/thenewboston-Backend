from celery import shared_task

from .services import tick_world


@shared_task(name='tasks.sweep_tribes')
def sweep_tribes():
    return tick_world()
