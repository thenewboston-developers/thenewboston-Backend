import logging

import discord
from asgiref.sync import sync_to_async
from discord.ext import commands

from thenewboston.general.init_django import init_django

init_django()  # we have to init Django before doing anything else

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from thenewboston.general.clients.llm import LLMClient, make_prompt_kwargs  # noqa: E402

USER_ROLE = 'user'
ASSISTANT_ROLE = 'assistant'

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot('/', intents=intents)

# TODO(dmu) HIGH: Cover bot logic with unittests: it is already complex enough


def is_ia(author):
    return author.id == settings.IA_DISCORD_USER_ID


def map_author_plaintext(author):
    return 'ia' if is_ia(author) else author.name


def map_author_structured(author):
    return ASSISTANT_ROLE if is_ia(author) else USER_ROLE


def messages_to_plaintext(messages):
    return '\n'.join(f'{map_author_plaintext(message.author)}: {message.content}' for message in messages)


def messages_to_structured(messages):
    structured_messages = []

    prev_role = None
    for message in messages:
        content = message.content

        if (role := map_author_structured(message.author)) == prev_role:
            # We need to merge messages to prevent the following error from Anthropic
            # messages: roles must alternate between "user" and "assistant", but found multiple "user" roles in a row
            assert structured_messages
            structured_messages[-1]['content'][0]['text'] += f'\n{content}'
        else:
            structured_messages.append({'role': role, 'content': [{'type': 'text', 'text': content}]})

        prev_role = role

    if structured_messages and structured_messages[0]['role'] != USER_ROLE:
        structured_messages.pop(0)

    return structured_messages


async def get_historical_messages(channel):
    # TODO(dmu) MEDIUM: Filter out only author's and IA's messages from the channel?
    return [message async for message in channel.history(limit=settings.DISCORD_MESSAGE_HISTORY_LIMIT)]


@bot.event
async def on_ready():
    user = bot.user
    logger.info('Discord Logged in as %s (ID: %s)', user, user.id)


async def on_message_implementation(message):
    if not (user := await sync_to_async(get_user_model().objects.get_or_none)(discord_user_id=message.author.id)):
        await message.reply('Please, register at https://thenewboston.com')
        return

    messages = (await get_historical_messages(message.channel))[::-1]

    # TODO(dmu) HIGH: Consider making just one LLM call that will return required response if necessary
    answer = LLMClient.get_instance().get_chat_completion(
        input_variables={'plain_text_message_history': messages_to_plaintext(messages)},
        tracked_user=user,
        **make_prompt_kwargs(settings.DISCORD_IS_RESPONSE_WARRANTED_PROMPT_NAME),
    )

    # TODO(dmu) LOW: Rename requiresResponse -> requires_response
    if answer.get('requiresResponse'):
        ias_response = LLMClient.get_instance().get_chat_completion(
            input_variables={
                'messages': messages_to_structured(messages),
                'text': message.content
            },
            tracked_user=user,
            tags=['discord_bot_response'],
            **make_prompt_kwargs(settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME)
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


if __name__ == '__main__':
    bot.run(settings.DISCORD_BOT_TOKEN, log_handler=None)
