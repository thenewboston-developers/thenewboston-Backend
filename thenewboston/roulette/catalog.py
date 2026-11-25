from thenewboston.casino.contracts import GameDefinition

from .rules import ROULETTE_V1, ROULETTE_V2

ROULETTE = GameDefinition(game='roulette', rules=(ROULETTE_V1, ROULETTE_V2), default_version=2, catalog_order=1)
