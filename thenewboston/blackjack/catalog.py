from thenewboston.casino.contracts import GameDefinition

from .rules import BLACKJACK_V1

BLACKJACK = GameDefinition(game='blackjack', rules=(BLACKJACK_V1,), default_min_bet=2, catalog_order=3)
