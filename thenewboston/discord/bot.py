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


@bot.command(name='ia')
async def ia_command(ctx, *, text):
    try:
        if not (user := await sync_to_async(get_user_model().objects.get_or_none)(discord_user_id=ctx.author.id)):
            # TODO(dmu) MEDIUM: Improve reply wording?
            await ctx.reply('Please, register at https://thenewboston.com')
            return

        historical_messages = await get_historical_messages(ctx)

        # TODO(dmu) HIGH: Interact with OpenAI in async way
        response = OpenAIClient.get_instance().get_chat_completion(
            settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME,
            input_variables={
                'messages': historical_messages,
                'text': text
            },
            tracked_user=user,
            tags=['discord_bot_response']
        )
        await ctx.reply(response)
    except Exception:
        logger.exception('An error occurred while processing "%s" command', ia_command.name)
        await ctx.reply('Oops.. Looks like something went wrong. Our team has been notified.')


async def get_historical_messages(ctx):
    results = []

    async for message in ctx.channel.history(limit=10):
        if '_ia' in str(message.author):
            results.append({'role': 'assistant', 'content': [{'type': 'text', 'text': message.content}]})
        else:
            content = message.content

            if content.startswith('/ia'):
                content = content[3:].strip()

            results.append({'role': 'user', 'content': [{'type': 'text', 'text': content}]})

    return results[::-1]


if __name__ == '__main__':
    bot.run(settings.DISCORD_BOT_TOKEN, log_handler=None)
