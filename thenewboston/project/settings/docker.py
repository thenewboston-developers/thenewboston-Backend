import os

if IN_DOCKER or os.path.isfile('/.dockerenv'):  # type: ignore # noqa: F821
    # We need this middleware to serve static files with DEBUG=False
    assert MIDDLEWARE[:1] == [  # type: ignore # noqa: F821
        'django.middleware.security.SecurityMiddleware'
    ]
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')  # type: ignore # noqa: F821
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    if not KEEP_DEFAULT_STATICFILES_STORAGE:  # type: ignore # noqa: F821 # Useful for testing staff locally
        STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
