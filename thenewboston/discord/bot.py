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


async def on_message_implementation(message):
    if not (user := await sync_to_async(get_user_model().objects.get_or_none)(discord_user_id=message.author.id)):
        await message.reply('Please, register at https://thenewboston.com')
        return

    # TODO(dmu) MEDIUM: Request message history just once and convert it to necessary format before LLM call
    plain_text_message_history = await get_plain_text_message_history(message.channel)

    # TODO(dmu) HIGH: Consider making just one LLM call that will return required response if necessary
    answer = OpenAIClient.get_instance().get_chat_completion(
        settings.DISCORD_IS_RESPONSE_WARRANTED_PROMPT_NAME,
        input_variables={'plain_text_message_history': plain_text_message_history},
        tracked_user=user
    )

    # TODO(dmu) LOW: Rename requiresResponse -> requires_response
    if answer.get('requiresResponse'):
        historical_messages = await get_historical_messages(message.channel)

        ias_response = OpenAIClient.get_instance().get_chat_completion(
            settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME,
            input_variables={
                'messages': historical_messages,
                'text': message.content
            },
            tracked_user=user,
            tags=['discord_bot_response']
        )
        await message.reply(ias_response)


@bot.event
async def on_message(message):
    # TODO(dmu) HIGH: Interact with OpenAI in async way

    if message.author == bot.user:
        return

    try:
        await on_message_implementation(message)
    except Exception:
        logger.exception('An error occurred while processing the message')
        await message.reply('Oops.. Looks like something went wrong. Our team has been notified.')


async def get_historical_messages(channel):
    # TODO(dmu) LOW: Make `get_historical_messages()` DRY with `get_plain_text_message_history()`
    results = []

    async for message in channel.history(limit=settings.DISCORD_MESSAGE_HISTORY_LIMIT):
        # TODO(dmu) LOW: If `_ia` supposed to be a suffix then use .endswith(). Also put `_ia` in a named
        #                constant or (better) custom setting
        if '_ia' in str(message.author):
            results.append({'role': 'assistant', 'content': [{'type': 'text', 'text': message.content}]})
        else:
            results.append({'role': 'user', 'content': [{'type': 'text', 'text': message.content}]})

    return results[::-1]


async def get_plain_text_message_history(channel):
    # TODO(dmu) LOW: Make `get_plain_text_message_history()` DRY with `get_historical_messages()`
    messages = []

    async for message in channel.history(limit=settings.DISCORD_MESSAGE_HISTORY_LIMIT):
        # TODO(dmu) LOW: If `_ia` supposed to be a suffix then use .endswith(). Also put `_ia` in a named
        #                constant or (better) custom setting
        author_name = 'ia' if '_ia' in str(message.author) else message.author.name
        messages.append(f'{author_name}: {message.content}')

    return '\n'.join(messages[::-1])


if __name__ == '__main__':
    bot.run(settings.DISCORD_BOT_TOKEN, log_handler=None)
