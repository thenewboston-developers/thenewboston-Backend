LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'filters': [],
        },
    },
    'loggers': {
        logger_name: {
            'level': 'WARNING',
            'propagate': True,
        } for logger_name in (
            # Too verbose loggers
            'asyncio',
            'django',
            'django.request',
            'django.db.backends',
            'django.template',
            'thenewboston',
        )
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console'],
    }
}
