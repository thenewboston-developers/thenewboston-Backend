from collections import namedtuple
from unittest.mock import patch

import pytest
from django.test import override_settings

from thenewboston.discord.bot import discord_messages_to_structured, on_ready

Author = namedtuple('Author', ['id'])
Message = namedtuple('Message', ['author', 'content'])


@pytest.mark.asyncio
async def test_on_ready():
    with patch('thenewboston.discord.bot.bot'):
        await on_ready()


@override_settings(IA_DISCORD_USER_ID=1)
def test_messages_to_structured():
    assert discord_messages_to_structured([Message(author=Author(id=2), content='hello')]) == [{
        'role': 'user',
        'content': [{
            'type': 'text',
            'text': 'hello'
        }]
    }]
    assert discord_messages_to_structured([
        Message(author=Author(id=2), content='hello'),
        Message(author=Author(id=2), content='world')
    ]) == [{
        'role': 'user',
        'content': [{
            'type': 'text',
            'text': 'hello\nworld'
        }]
    }]
    assert discord_messages_to_structured([
        Message(author=Author(id=2), content='hello'),
        Message(author=Author(id=1), content='world')
    ]) == [
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'world'
            }]
        },
    ]
    assert discord_messages_to_structured([
        Message(author=Author(id=2), content='hello'),
        Message(author=Author(id=1), content='world'),
        Message(author=Author(id=2), content='bye')
    ]) == [
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'world'
            }]
        },
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'bye'
            }]
        },
    ]
    assert discord_messages_to_structured([
        Message(author=Author(id=2), content='hello'),
        Message(author=Author(id=1), content='world'),
        Message(author=Author(id=2), content='mine'),
        Message(author=Author(id=2), content='bye')
    ]) == [
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'world'
            }]
        },
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'mine\nbye'
            }]
        },
    ]

    assert discord_messages_to_structured([
        Message(author=Author(id=1), content='hello'),
        Message(author=Author(id=2), content='world')
    ]) == [{
        'role': 'user',
        'content': [{
            'type': 'text',
            'text': 'world'
        }]
    }]
