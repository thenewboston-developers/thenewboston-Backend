from django.apps import AppConfig


class RouletteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.roulette'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import ROULETTE

        registry.register(ROULETTE)
