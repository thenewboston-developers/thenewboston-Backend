from thenewboston.casino.contracts import GameDefinition

from .rules import SLOTS_V1

SLOTS = GameDefinition(game='slots', rules=(SLOTS_V1,), catalog_order=0)
