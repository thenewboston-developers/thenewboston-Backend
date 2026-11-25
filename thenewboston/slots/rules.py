"""Slots version 1. Preserve these mappings for replaying historical fairness receipts."""

from thenewboston.casino.contracts import GameRules

SLOT_WEIGHTS = ((0, 5885), (1, 1600), (2, 2000), (5, 400), (10, 100), (50, 10), (100, 5))
SLOT_SYMBOLS = {
    0: ['cherry', 'lemon', 'bar'],
    1: ['cherry'] * 3,
    2: ['lemon'] * 3,
    5: ['bell'] * 3,
    10: ['bar'] * 3,
    50: ['diamond'] * 3,
    100: ['seven'] * 3,
}


class SlotsRules(GameRules):
    def normalize_selection(self, selection):
        if selection not in (None, {}):
            raise ValueError('Slots does not accept a selection.')
        return {}

    def multiplier(self, selection):
        return self.max_multiplier

    def outcome(self, random, selection):
        draw = random.below(10000)
        cursor = 0
        for multiplier, weight in SLOT_WEIGHTS:
            cursor += weight
            if draw < cursor:
                return {'draw': draw, 'multiplier': multiplier, 'symbols': SLOT_SYMBOLS[multiplier]}
        raise AssertionError('Invalid slot probability table')

    def catalog_data(self, maximum_bet):
        return {
            'payout_table': [
                {'multiplier': multiplier, 'probability': weight / 10000} for multiplier, weight in SLOT_WEIGHTS
            ]
        }

    def verify(self):
        if sum(weight for _, weight in SLOT_WEIGHTS) != 10000:
            raise ValueError('Slot probabilities do not sum to 100%.')
        if sum(multiplier * weight for multiplier, weight in SLOT_WEIGHTS) != 9600:
            raise ValueError('Slot RTP is not 96%.')
        if max(multiplier for multiplier, _ in SLOT_WEIGHTS) != 100 or self.max_multiplier != 100:
            raise ValueError('Slot maximum payout is not 100x.')


SLOTS_V1 = SlotsRules(
    game='slots', version=1, name='Slots', max_multiplier=100, house_edge=0.04, catalog_multiplier=100
)
