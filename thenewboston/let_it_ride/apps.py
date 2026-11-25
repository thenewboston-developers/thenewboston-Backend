from django.apps import AppConfig


class LetItRideConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.let_it_ride'

    def ready(self):
        from thenewboston.casino.registry import registry

        from .catalog import LET_IT_RIDE

        registry.register(LET_IT_RIDE)
