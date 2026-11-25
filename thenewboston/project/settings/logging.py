LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
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
        }
        for logger_name in (
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
    },
}

# Websocket connections that are rejected, or would be once ENFORCE_WEBSOCKET_AUTHENTICATION is on. INFO keeps them in
# the server log without turning each one into a Sentry event.
LOGGING['loggers']['thenewboston.general.consumers.authenticated_user'] = {
    'level': 'INFO',
    'propagate': True,
}
