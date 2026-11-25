from django.apps import AppConfig


class SocialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.social'

    def ready(self):
        from .signals import connect_signals

        connect_signals()
