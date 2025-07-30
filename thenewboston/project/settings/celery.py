CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    'update_trade_history': {
        'task': 'tasks.update_trade_history',
        'schedule': 60 * 10,  # 10 minutes
    },
}
