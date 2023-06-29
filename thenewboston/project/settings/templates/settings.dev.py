DEBUG = True
SECRET_KEY = 'django-insecure--08t722@a3nhs))9%p=fzpda1@3y9c*-kprqzd9@3*w0o18@qe'

SIGNING_KEY = ''
ACCOUNT_NUMBER = ''

LOGGING['formatters']['colored'] = {  # type: ignore
    '()': 'colorlog.ColoredFormatter',
    'format': '%(log_color)s%(asctime)s %(levelname)s %(name)s %(bold_white)s%(message)s',
}
LOGGING['loggers']['thenewboston']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['formatter'] = 'colored'  # type: ignore
