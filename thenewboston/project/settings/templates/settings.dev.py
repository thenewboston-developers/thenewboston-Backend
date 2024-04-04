DEBUG = True
SECRET_KEY = 'django-insecure--08t722@a3nhs))9%p=fzpda1@3y9c*-kprqzd9@3*w0o18@qe'

LOGGING['formatters']['colored'] = {  # type: ignore
    '()': 'colorlog.ColoredFormatter',
    'format': '%(log_color)s%(asctime)s %(levelname)s %(name)s %(bold_white)s%(message)s',
}
LOGGING['loggers']['thenewboston']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['formatter'] = 'colored'  # type: ignore

ACCOUNT_NUMBER = '074463d2996f2942d8c724304fafe121f76c376ec2c35c8a2b35ebd08f226cd9'
SIGNING_KEY = '756eb20e5569a0c906ccb813263aa27159aeafa07d7208f860ae290c03066c51'

OPENAI_API_KEY = 'abc123'  # replace with actual value
PROMPTLAYER_API_KEY = 'abc123'  # replace with actual value
GITHUB_API_ACCESS_TOKEN = 'abc123'  # replace with actual value

ENV_NAME = 'local-development'
