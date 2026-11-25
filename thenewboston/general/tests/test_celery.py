import importlib
import importlib.util
import pkgutil

from django.conf import settings

import thenewboston
from thenewboston.project.celery import app


def test_every_scheduled_task_is_in_a_module_the_worker_imports():
    # Beat keeps sending a task the worker never imported, and every run then fails with a KeyError. Import every
    # app's tasks so a scheduled task is found wherever it is defined, then check its module is in the include list.
    for module in pkgutil.iter_modules(thenewboston.__path__):
        name = f'thenewboston.{module.name}.tasks'
        if module.ispkg and importlib.util.find_spec(name):
            importlib.import_module(name)

    for schedule_name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        assert entry['task'] in app.tasks, schedule_name
        assert app.tasks[entry['task']].__module__ in app.conf.include, schedule_name
