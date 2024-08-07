from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def discord_context():
    context = MagicMock()
    context.reply = AsyncMock()
    return context
