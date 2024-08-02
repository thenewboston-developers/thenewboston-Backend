from django.apps import AppConfig

from thenewboston.discord.utils.bot import initialize_client


class DiscordConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'discord'

    def ready(self):
        # TODO(Muhammad): Need to spin up the discord service separately.
        # this would block the django server
        initialize_client()
