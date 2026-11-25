"""Immutable casino rules. New game behavior is registered under a new (game, version) key."""

from dataclasses import dataclass

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
RED_NUMBERS = frozenset((1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36))
ROULETTE_TYPES = {
    'red': ('Red', 2),
    'black': ('Black', 2),
    'odd': ('Odd', 2),
    'even': ('Even', 2),
    'low': ('1–18', 2),
    'high': ('19–36', 2),
    'dozen': ('Dozen', 3),
    'column': ('Column', 3),
    'number': ('Single number', 36),
}


@dataclass(frozen=True)
class Rules:
    game: str
    version: int
    name: str
    max_multiplier: int
    house_edge: float
    settlement_mode: str = 'instant'

    def normalize_selection(self, selection):
        if self.game == 'slots':
            if selection not in (None, {}):
                raise ValueError('Slots does not accept a selection.')
            return {}
        if (
            not isinstance(selection, dict)
            or not isinstance(selection.get('type'), str)
            or selection['type'] not in ROULETTE_TYPES
        ):
            raise ValueError('Select a supported roulette bet type.')
        kind = selection['type']
        if kind in ('number', 'dozen', 'column'):
            value = selection.get('value')
            low, high = (0, 36) if kind == 'number' else (1, 3)
            if set(selection) != {'type', 'value'} or type(value) is not int or not low <= value <= high:
                raise ValueError(f'{kind} must be a whole number from {low} to {high}.')
            return {'type': kind, 'value': value}
        if set(selection) != {'type'}:
            raise ValueError('This roulette bet type does not accept a value.')
        return {'type': kind}

    def multiplier(self, selection):
        return self.max_multiplier if self.game == 'slots' else ROULETTE_TYPES[selection['type']][1]

    def outcome(self, random, selection):
        if self.game == 'slots':
            draw = random.below(10000)
            cursor = 0
            for multiplier, weight in SLOT_WEIGHTS:
                cursor += weight
                if draw < cursor:
                    return {'draw': draw, 'multiplier': multiplier, 'symbols': SLOT_SYMBOLS[multiplier]}
            raise AssertionError('Invalid slot probability table')
        number = random.below(37)
        color = 'green' if number == 0 else 'red' if number in RED_NUMBERS else 'black'
        kind, value = selection['type'], selection.get('value')
        wins = {
            'red': color == 'red',
            'black': color == 'black',
            'odd': number > 0 and number % 2 == 1,
            'even': number > 0 and number % 2 == 0,
            'low': 1 <= number <= 18,
            'high': 19 <= number <= 36,
            'number': number == value,
            'dozen': number > 0 and (number - 1) // 12 + 1 == value,
            'column': number > 0 and (number - 1) % 3 + 1 == value,
        }
        return {'number': number, 'color': color, 'multiplier': self.multiplier(selection) if wins[kind] else 0}


RULES = {
    ('slots', 1): Rules('slots', 1, 'Slots', 100, 0.04),
    ('roulette', 1): Rules('roulette', 1, 'Roulette', 36, 1 / 37),
}


def get_rules(game, version):
    try:
        return RULES[(game, version)]
    except (KeyError, TypeError) as exc:
        raise ValueError('Unsupported game or rules version.') from exc
