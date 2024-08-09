from collections import namedtuple
from unittest.mock import patch

import pytest
from django.test import override_settings

from thenewboston.discord.bot import messages_to_structured, on_ready

Author = namedtuple('Author', ['id'])
Message = namedtuple('Message', ['author', 'content'])


@pytest.mark.asyncio
async def test_on_ready():
    with patch('thenewboston.discord.bot.bot'):
        await on_ready()


@override_settings(IA_DISCORD_USER_ID=1234)
def test_messages_to_structured():
    assert messages_to_structured([Message(author=Author(id=1234), content='hello')]) == [{
        'role': 'assistant',
        'content': [{
            'type': 'text',
            'text': 'hello'
        }]
    }]
    assert messages_to_structured([
        Message(author=Author(id=1234), content='hello'),
        Message(author=Author(id=1234), content='world')
    ]) == [{
        'role': 'assistant',
        'content': [{
            'type': 'text',
            'text': 'hello\nworld'
        }]
    }]
    assert messages_to_structured([
        Message(author=Author(id=1234), content='hello'),
        Message(author=Author(id=10), content='world')
    ]) == [
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'world'
            }]
        },
    ]
    assert messages_to_structured([
        Message(author=Author(id=1234), content='hello'),
        Message(author=Author(id=10), content='world'),
        Message(author=Author(id=1234), content='bye')
    ]) == [
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'world'
            }]
        },
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'bye'
            }]
        },
    ]
    assert messages_to_structured([
        Message(author=Author(id=1234), content='hello'),
        Message(author=Author(id=10), content='world'),
        Message(author=Author(id=10), content='mine'),
        Message(author=Author(id=1234), content='bye')
    ]) == [
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'hello'
            }]
        },
        {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': 'world\nmine'
            }]
        },
        {
            'role': 'assistant',
            'content': [{
                'type': 'text',
                'text': 'bye'
            }]
        },
    ]
