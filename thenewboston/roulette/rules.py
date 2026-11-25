"""Single-zero Roulette version 1. Preserve selections and outcomes for historical receipts."""

from thenewboston.casino.contracts import GameRules

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


class RouletteRules(GameRules):
    def normalize_selection(self, selection):
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
        return ROULETTE_TYPES[selection['type']][1]

    def outcome(self, random, selection):
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

    def catalog_data(self, maximum_bet):
        return {
            'bet_types': [
                {'id': kind, 'label': label, 'multiplier': multiplier, 'max_bet': maximum_bet(multiplier)}
                for kind, (label, multiplier) in ROULETTE_TYPES.items()
            ]
        }

    def verify(self):
        if len(RED_NUMBERS) != 18 or not RED_NUMBERS <= set(range(1, 37)):
            raise ValueError('Roulette must have 18 red numbers on its single-zero wheel.')
        winning_counts = {
            'red': 18,
            'black': 18,
            'odd': 18,
            'even': 18,
            'low': 18,
            'high': 18,
            'dozen': 12,
            'column': 12,
            'number': 1,
        }
        if set(ROULETTE_TYPES) != set(winning_counts) or any(
            multiplier * winning_counts[kind] != 36 for kind, (_, multiplier) in ROULETTE_TYPES.items()
        ):
            raise ValueError('Roulette payout tables must return 36/37 of stakes.')
        if self.max_multiplier != 36 or self.catalog_multiplier != 2:
            raise ValueError('Roulette maximum or catalog multiplier is invalid.')


ROULETTE_V1 = RouletteRules(
    game='roulette', version=1, name='Roulette', max_multiplier=36, house_edge=1 / 37, catalog_multiplier=2
)
