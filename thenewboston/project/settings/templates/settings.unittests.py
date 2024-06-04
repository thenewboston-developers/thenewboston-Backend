MIDDLEWARE += ('thenewboston.general.middleware.LoggingMiddleware',)  # type: ignore
LOGGING['formatters']['colored'] = {  # type: ignore
    '()': 'colorlog.ColoredFormatter',
    'format': '%(log_color)s%(asctime)s %(levelname)s %(name)s %(bold_white)s%(message)s',
}
LOGGING['loggers']['thenewboston']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['formatter'] = 'colored'  # type: ignore

ENV_NAME = 'local-unittests'

# Uncomment the following line to record vcrpy cassette
# IS_CASSETTE_RECORDING = False
