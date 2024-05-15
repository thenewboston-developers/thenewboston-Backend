CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = 3600
CELERY_BEAT_SCHEDULE = {
    'sync-contributions': {
        'task': 'tasks.sync_contributions',
        'schedule': 60 * 60,  # 1 hour
    },
    'reward-manual-contributions': {
        'task': 'tasks.reward_manual_contributions',
        'schedule': 60 * 60,  # 1 hour
    },
}
