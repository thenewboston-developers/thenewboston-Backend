from unittest.mock import patch

import pytest

from thenewboston.discord.bot import ia_command, on_ready


@pytest.mark.asyncio
async def test_on_ready():
    with patch('thenewboston.discord.bot.bot'):
        await on_ready()


# transaction=True help commiting other transactions, so database changes are visible from different
# coroutines and threads
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ai_command__basic_reply(bucky, discord_context):
    ctx = discord_context
    ctx.author.id = bucky.discord_user_id
    with patch(
        'thenewboston.general.clients.openai.OpenAIClient.get_chat_completion', return_value='short response'
    ) as get_chat_completion_mock:
        await ia_command(ctx, text='give me the shortest reply possible')

    get_chat_completion_mock.assert_called_once_with(
        'create-response',
        input_variables={'question': 'give me the shortest reply possible'},
        tracked_user=bucky,
        tags=['discord_bot_response']
    )
    ctx.reply.assert_awaited_once_with('short response')


# transaction=True help commiting other transactions, so database changes are visible from different
# coroutines and threads
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ai_command__no_user(discord_context):
    ctx = discord_context
    ctx.author.id = 999999999999
    await ia_command(ctx, text='give me the shortest reply possible')
    ctx.reply.assert_awaited_once_with('Please, register at https://thenewboston.com')
