from thenewboston.casino.contracts import GameDefinition

from .engine import BETS
from .rules import LET_IT_RIDE_V1

LET_IT_RIDE = GameDefinition(game='let_it_ride', rules=(LET_IT_RIDE_V1,), default_min_bet=BETS, catalog_order=4)
