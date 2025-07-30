import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')

app = Celery('thenewboston.project', include=['thenewboston.exchange.tasks'])
app.config_from_object('django.conf:settings', namespace='CELERY')
