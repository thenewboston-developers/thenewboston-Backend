import asyncio
import os
import threading

from django.apps import AppConfig
from django.conf import settings

from thenewboston.discord.utils.bot import initialize_client


class DiscordConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'discord'
    bot_initialized = False

    def ready(self):
        """
        Start the Discord bot client in a non-blocking way using a separate thread, only if not already started.
        """
        if not DiscordConfig.bot_initialized and not os.environ.get('RUN_MAIN'):
            if settings.DISCORD_BOT_TOKEN:
                thread = threading.Thread(target=self.start_discord_bot, daemon=True)
                thread.start()
                DiscordConfig.bot_initialized = True

    def start_discord_bot(self):
        """
        Initializes the asyncio event loop and runs the Discord bot.
        """
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()
            loop.create_task(initialize_client())
            loop.run_forever()
        except Exception as e:
            print(f'Failed to start Discord bot: {e}')
