import logging

from celery import shared_task

from .utils.cache import warm_popular_users_cache

logger = logging.getLogger(__name__)


@shared_task
def warm_user_cache():
    """
    Periodic task to warm the cache with popular users.
    Should be scheduled to run every hour via Celery Beat.
    """
    try:
        warm_popular_users_cache()
        logger.info('Successfully warmed popular users cache')
        return 'Cache warming completed'
    except Exception as e:
        logger.error(f'Failed to warm cache: {e}')
        raise
