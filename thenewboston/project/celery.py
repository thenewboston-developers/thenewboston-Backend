import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')
app = Celery(
    'thenewboston.project',
    include=['thenewboston.project.tasks'],
)
app.config_from_object('django.conf:settings', namespace='CELERY')

if __name__ == '__main__':
    app.start()
