from thenewboston.casino.contracts import GameDefinition

from .rules import VIDEO_POKER_V1

VIDEO_POKER = GameDefinition(game='video_poker', rules=(VIDEO_POKER_V1,), catalog_order=5)
