"""Twelve-row Plinko version 1. Preserve this path mapping and payout table for historical receipts."""

from math import comb

from thenewboston.casino.contracts import GameRules

PLINKO_ROWS = 12
PLINKO_PATHS = 2**PLINKO_ROWS
PLINKO_MULTIPLIERS = (50, 18, 8, 3, 1, 0, 0, 0, 1, 3, 8, 18, 50)
PLINKO_RETURN = 3898


class PlinkoRules(GameRules):
    def normalize_selection(self, selection):
        if selection is not None and (not isinstance(selection, dict) or selection):
            raise ValueError('Plinko does not accept a selection.')
        return {}

    def multiplier(self, selection):
        return self.max_multiplier

    def outcome(self, random, selection):
        # A uniform 12-bit integer represents twelve independent, equally likely left/right bounces.
        draw = random.below(PLINKO_PATHS)
        path = [(draw >> shift) & 1 for shift in reversed(range(PLINKO_ROWS))]
        slot = sum(path)
        return {'draw': draw, 'path': path, 'slot': slot, 'multiplier': PLINKO_MULTIPLIERS[slot]}

    def catalog_data(self, maximum_bet):
        return {
            'rows': PLINKO_ROWS,
            'payout_table': [
                {'slot': slot, 'multiplier': multiplier, 'probability': comb(PLINKO_ROWS, slot) / PLINKO_PATHS}
                for slot, multiplier in enumerate(PLINKO_MULTIPLIERS)
            ],
        }

    def verify(self):
        if PLINKO_ROWS != 12 or len(PLINKO_MULTIPLIERS) != PLINKO_ROWS + 1:
            raise ValueError('Plinko must have twelve rows and thirteen pockets.')
        if PLINKO_MULTIPLIERS != PLINKO_MULTIPLIERS[::-1] or any(
            type(multiplier) is not int or multiplier < 0 for multiplier in PLINKO_MULTIPLIERS
        ):
            raise ValueError('Plinko payouts must be symmetric nonnegative whole-number multipliers.')
        weights = [comb(PLINKO_ROWS, slot) for slot in range(PLINKO_ROWS + 1)]
        if (
            sum(weights) != PLINKO_PATHS
            or sum(multiplier * weight for multiplier, weight in zip(PLINKO_MULTIPLIERS, weights, strict=True))
            != PLINKO_RETURN
        ):
            raise ValueError('Plinko RTP must be 3898/4096.')
        if max(PLINKO_MULTIPLIERS) != 50 or self.max_multiplier != 50 or self.catalog_multiplier != 50:
            raise ValueError('Plinko maximum payout must be 50x.')
        if self.house_edge != 1 - PLINKO_RETURN / PLINKO_PATHS:
            raise ValueError('Plinko house edge does not match its payout table.')


PLINKO_V1 = PlinkoRules(
    game='plinko',
    version=1,
    name='Plinko',
    max_multiplier=50,
    house_edge=1 - PLINKO_RETURN / PLINKO_PATHS,
    catalog_multiplier=50,
)
