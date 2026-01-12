CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    'expire_connect_five_challenges': {
        'task': 'tasks.expire_connect_five_challenges',
        'schedule': 30,
    },
    'sweep_connect_five_timeouts': {
        'task': 'tasks.sweep_connect_five_timeouts',
        'schedule': 15,
    },
    'update_trade_history': {
        'task': 'tasks.update_trade_history',
        'schedule': 60 * 10,  # 10 minutes
    },
}
