from django.apps import AppConfig


class SlotsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.slots'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import SLOTS

        registry.register(SLOTS)
