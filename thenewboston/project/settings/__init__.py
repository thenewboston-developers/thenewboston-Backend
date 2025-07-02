import os.path
from pathlib import Path

from split_settings.tools import include, optional

from thenewboston.general.utils.pytest import is_pytest_running

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENVVAR_SETTINGS_PREFIX = 'THENEWBOSTON_SETTING_'
LOCAL_SETTINGS_PATH = os.getenv(f'{ENVVAR_SETTINGS_PREFIX}LOCAL_SETTINGS_PATH')

if not LOCAL_SETTINGS_PATH:
    LOCAL_SETTINGS_PATH = f'local/settings{".unittests" if is_pytest_running() else ".dev"}.py'

if not os.path.isabs(LOCAL_SETTINGS_PATH):
    LOCAL_SETTINGS_PATH = str(BASE_DIR / LOCAL_SETTINGS_PATH)

include(
    'base.py',
    'logging.py',
    'rest_framework.py',
    'channels.py',
    'aws.py',
    'misc.py',
    'custom.py',
    'testing.py',
    optional(LOCAL_SETTINGS_PATH),
    'envvars.py',
    'sentry.py',
    'post.py',
)
