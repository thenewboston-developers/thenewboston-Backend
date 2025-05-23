if IS_DEPLOYED:  # type: ignore # noqa: F821
    assert MIDDLEWARE[:1] == [  # type: ignore # noqa: F821
        'django.middleware.security.SecurityMiddleware'
    ]
    # We need this middleware to serve static files with DEBUG=False
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')  # type: ignore # noqa: F821
    # TODO(dmu) HIGH: DEFAULT_FILE_STORAGE is deprecated. Refactor
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'location': 'media',  # folder inside the bucket for media files
                'file_overwrite': False,
                'default_acl': None,
            },
        },
        'staticfiles': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'location': 'static',  # folder inside the bucket for static files
                'file_overwrite': True,
                'default_acl': None,
            },
        },
    }
