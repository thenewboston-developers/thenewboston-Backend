import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')

app = Celery(
    'thenewboston.project',
    include=[
        'thenewboston.backgammon.tasks',
        'thenewboston.battleship.tasks',
        'thenewboston.checkers.tasks',
        'thenewboston.connect_five.tasks',
        'thenewboston.dots_and_boxes.tasks',
        'thenewboston.exchange.tasks',
        'thenewboston.general.tasks',
        'thenewboston.hex.tasks',
        'thenewboston.mancala.tasks',
        'thenewboston.product_analytics.tasks',
        'thenewboston.reversi.tasks',
        'thenewboston.social.tasks',
    ],
)
app.config_from_object('django.conf:settings', namespace='CELERY')
