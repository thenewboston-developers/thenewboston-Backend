from thenewboston.casino.contracts import GameDefinition

from .rules import SLOTS_V1, SLOTS_V2

SLOTS = GameDefinition(game='slots', rules=(SLOTS_V1, SLOTS_V2), default_version=2, catalog_order=0)
