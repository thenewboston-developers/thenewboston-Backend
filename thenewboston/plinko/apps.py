from django.apps import AppConfig


class PlinkoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.plinko'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import PLINKO

        registry.register(PLINKO)
