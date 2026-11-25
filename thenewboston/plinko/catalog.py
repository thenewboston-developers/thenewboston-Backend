from thenewboston.casino.contracts import GameDefinition

from .rules import PLINKO_V1

PLINKO = GameDefinition(game='plinko', rules=(PLINKO_V1,), catalog_order=2)
