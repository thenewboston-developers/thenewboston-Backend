import logging

import discord
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model

from thenewboston.discord.constants import IA_DISCORD_COMMAND_PREFIX, SOMETHING_WENT_WRONG
from thenewboston.ia.utils.ia import ask_ia

logger = logging.getLogger(__name__)


class DiscordBotClient(discord.Client):
    """
    A Discord client that responds to specific commands with integrated AI responses.
    """

    async def on_ready(self):
        """
        Executed once the bot is ready and logged in, logging bot's current user ID.
        """
        logger.info(f'Discord Logged in as {self.user} (ID: {self.user.id})')

    async def on_message(self, message):
        """
        Handles incoming messages by responding to specific commands.
        """
        try:
            if message.author.id == self.user.id:
                return  # Ignore messages from the bot itself

            User = get_user_model()
            user = await sync_to_async(User.objects.get)(id=1)

            if message.content.startswith(IA_DISCORD_COMMAND_PREFIX):
                question = message.content[len(IA_DISCORD_COMMAND_PREFIX):]
                result = ask_ia(question.strip(), user)
                await message.reply(result)
        except Exception as e:
            logger.exception('An error occurred in discord on_message: %s', e)
            await message.reply(SOMETHING_WENT_WRONG)


def initialize_client():
    """
    Initializes and runs the Discord bot client with specified intents to handle message content.
    """
    try:
        intents = discord.Intents.default()
        intents.message_content = True  # Allow the bot to read message content

        client = DiscordBotClient(intents=intents)
        client.run(settings.DISCORD_BOT_TOKEN)  # Run the client with the bot token from settings
    except discord.LoginFailure as e:
        logger.exception('Failed to log in to Discord: %s', e)
    except Exception as e:
        logger.exception('An error occurred: %s', e)
