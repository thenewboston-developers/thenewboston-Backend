from django.apps import AppConfig


class ProductAnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thenewboston.product_analytics'

    def ready(self):
        from .client import initialize_client
        from .signals import connect_signals

        initialize_client()
        connect_signals()
