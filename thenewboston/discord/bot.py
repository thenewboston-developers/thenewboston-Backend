import logging

import discord
from asgiref.sync import sync_to_async
from discord.ext import commands

from thenewboston.general.init_django import init_django

init_django()  # we have to init Django before doing anything else

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from thenewboston.general.clients.openai import OpenAIClient  # noqa: E402

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot('/', intents=intents)


@bot.event
async def on_ready():
    user = bot.user
    logger.info('Discord Logged in as %s (ID: %s)', user, user.id)


@bot.command()
async def ia(ctx, *, text):
    try:
        user = await sync_to_async(get_user_model().objects.get)(id=1)
        # TODO(dmu) HIGH: Interact with OpenAI in async way
        response = OpenAIClient.get_instance().get_chat_completion(
            settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME,
            # TODO(dmu) LOW: Rename `question` to `text`, since the text provided is not necessarily a question
            input_variables={'question': text},
            tracked_user=user,
            tags=['discord_bot_response']
        )
        await ctx.send(response)
    except Exception:
        logger.exception('An error occurred in discord on_message')
        await ctx.reply('Oops.. Looks like something went wrong. Our team has been notified.')


bot.run(settings.DISCORD_BOT_TOKEN, log_handler=None)
