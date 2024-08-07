from unittest.mock import patch

import pytest

from thenewboston.discord.bot import on_ready


@pytest.mark.asyncio
async def test_on_ready():
    with patch('thenewboston.discord.bot.bot'):
        await on_ready()
