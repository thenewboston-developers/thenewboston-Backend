from django.apps import AppConfig


class BlackjackConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.blackjack'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import BLACKJACK

        registry.register(BLACKJACK)
