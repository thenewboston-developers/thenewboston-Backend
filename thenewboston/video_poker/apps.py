from django.apps import AppConfig


class VideoPokerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.video_poker'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import VIDEO_POKER

        registry.register(VIDEO_POKER)
