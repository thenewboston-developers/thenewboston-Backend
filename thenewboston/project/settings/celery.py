CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = 3600
CELERY_BEAT_SCHEDULE = {
    'sync-contributions-every-5-minutes': {
        'task': 'tasks.sync_contributions',
        'schedule': 60 * 5,  # 5 minutes
    },
}
