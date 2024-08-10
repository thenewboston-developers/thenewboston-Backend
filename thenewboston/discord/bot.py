import json
import logging

import discord
from asgiref.sync import sync_to_async
from discord.ext import commands
from openai import OpenAI

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


def discord_messages_to_plaintext(discord_messages):
    return '\n'.join(f'{map_author_plaintext(message.author)}: {message.content}' for message in discord_messages)


def discord_messages_to_structured(discord_messages):
    structured_messages = []

    for discord_message in discord_messages:
        role = map_author_structured(discord_message.author)
        structured_messages.append({'role': role, 'content': [{'type': 'text', 'text': discord_message.content}]})

    return structured_messages


async def get_historical_discord_messages(channel):
    # TODO(dmu) MEDIUM: Filter out only author's and Ia's messages from the channel?
    return [message async for message in channel.history(limit=settings.DISCORD_MESSAGE_HISTORY_LIMIT)]


def is_ia(author):
    return author.id == settings.IA_DISCORD_USER_ID


def map_author_plaintext(author):
    return 'ia' if is_ia(author) else author.name


def map_author_structured(author):
    return ASSISTANT_ROLE if is_ia(author) else USER_ROLE


@bot.event
async def on_ready():
    user = bot.user
    logger.info('Discord Logged in as %s (ID: %s)', user, user.id)


def get_perplexity_response(query):
    """Get a response from Perplexity AI for real-time or up-to-date information"""
    client = OpenAI(api_key=settings.PERPLEXITY_API_KEY, base_url='https://api.perplexity.ai')

    messages = [{
        'role': 'system',
        'content': 'You are an AI assistant that provides up-to-date information. '
    }, {
        'role': 'user',
        'content': query
    }]

    response = client.chat.completions.create(model='llama-3.1-sonar-large-128k-online', messages=messages)

    return response.choices[0].message.content


async def on_message_implementation(message):
    if not (user := await sync_to_async(get_user_model().objects.get_or_none)(discord_user_id=message.author.id)):
        await message.reply('Please, register at https://thenewboston.com')
        return

    discord_messages = (await get_historical_discord_messages(message.channel))[::-1]

    is_response_warranted = LLMClient.get_instance().get_chat_completion(
        input_variables={'plain_text_message_history': discord_messages_to_plaintext(discord_messages)},
        tracked_user=user,
        **make_prompt_kwargs(settings.DISCORD_IS_RESPONSE_WARRANTED_PROMPT_NAME),
    )

    if is_response_warranted.get('requires_response') is False:
        return

    structured_messages = discord_messages_to_structured(discord_messages)

    first_response = LLMClient.get_instance().get_chat_completion(
        format_result=False,
        input_variables={
            'messages': structured_messages,
        },
        tracked_user=user,
        tags=['discord_bot_response'],
        **make_prompt_kwargs(settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME)
    )
    first_response_prompt_blueprint = first_response['prompt_blueprint']
    first_response_prompt_template = first_response_prompt_blueprint['prompt_template']
    first_response_messages = first_response_prompt_template['messages']
    latest_llm_message = first_response_messages[-1]

    if latest_llm_message['content'][0]['text']:
        await message.reply(latest_llm_message['content'][0]['text'])

    if latest_llm_message['tool_calls']:
        available_functions = {
            'get_perplexity_response': get_perplexity_response,
        }
        new_messages = first_response_messages

        for tool_call in latest_llm_message['tool_calls']:
            function_name = tool_call['function']['name']
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call['function']['arguments'])
            function_response = function_to_call(query=function_args.get('query'))
            new_messages.append({
                'tool_call_id': tool_call['id'],
                'role': 'tool',
                'name': function_name,
                'content': [{
                    'type': 'text',
                    'text': function_response
                }],
            })

        second_response = LLMClient.get_instance().get_chat_completion(
            format_result=False,
            input_variables={
                'messages': new_messages,
            },
            tracked_user=user,
            tags=['discord_bot_response'],
            **make_prompt_kwargs(settings.DISCORD_CREATE_RESPONSE_PROMPT_NAME)
        )
        second_response_prompt_blueprint = second_response['prompt_blueprint']
        second_response_prompt_template = second_response_prompt_blueprint['prompt_template']
        second_response_messages = second_response_prompt_template['messages']
        final_llm_message = second_response_messages[-1]

        await message.reply(final_llm_message['content'][0]['text'])


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
