import os

os.environ['PYTEST_RUNNING'] = 'true'

from thenewboston.general.tests.fixtures import *  # noqa: F401, F403, E402
from thenewboston.users.tests.fixtures import *  # noqa: F401, F403, E402
