DEBUG = False
SECRET_KEY = NotImplemented

ALLOWED_HOSTS: list[str] = ['*']
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS: list[str] = []

INTERNAL_IPS = [
    '127.0.0.1',
]

APPEND_SLASH = False

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'storages',

    # Apps
    'thenewboston.art.apps.ArtConfig',
    'thenewboston.authentication.apps.AuthenticationConfig',
    'thenewboston.contributions.apps.ContributionsConfig',
    'thenewboston.cores.apps.CoresConfig',
    'thenewboston.exchange.apps.ExchangeConfig',
    'thenewboston.general',
    'thenewboston.github.apps.GithubConfig',
    'thenewboston.ia.apps.IaConfig',
    'thenewboston.notifications.apps.NotificationsConfig',
    'thenewboston.shop.apps.ShopConfig',
    'thenewboston.social.apps.SocialConfig',
    'thenewboston.university.apps.UniversityConfig',
    'thenewboston.users.apps.UsersConfig',
    'thenewboston.wallets.apps.WalletsConfig',
]

# MIDDLEWARE is list because we need insert a middleware in `post.py`
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'thenewboston.project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'thenewboston.project.asgi.application'
WSGI_APPLICATION = 'thenewboston.project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'thenewboston',
        'USER': 'thenewboston',
        'PASSWORD': 'thenewboston',
        'HOST': 'localhost',
        'PORT': '5432',
        'ATOMIC_REQUESTS': True,
        'CONN_MAX_AGE': 0,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTH_USER_MODEL = 'users.User'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # type: ignore # noqa: F821

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # type: ignore # noqa: F821

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
