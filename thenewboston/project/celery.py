import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')
app = Celery(
    'thenewboston.project',
    backend='redis://localhost:6379/0',
    broker='redis://localhost:6379/0',
    include=['thenewboston.project.tasks'],
)
app.conf.update(result_expires=3600)

if __name__ == '__main__':
    app.start()
