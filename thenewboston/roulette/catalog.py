from thenewboston.casino.contracts import GameDefinition

from .rules import ROULETTE_V1

ROULETTE = GameDefinition(game='roulette', rules=(ROULETTE_V1,), catalog_order=1)
