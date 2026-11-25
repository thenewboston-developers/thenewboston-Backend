"""Single-zero Roulette. Version 1 settles one spot per spin; version 2 settles chips on several spots.

Preserve each version's selections and outcomes for historical receipts."""

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


TYPE_ORDER = {kind: position for position, kind in enumerate(ROULETTE_TYPES)}


def pocket_color(number):
    if number == 0:
        return 'green'
    return 'red' if number in RED_NUMBERS else 'black'


def spot_wins(kind, value, number):
    """Whether a bet on one spot wins when the ball lands on `number`. Zero loses every outside bet."""
    if kind == 'number':
        return number == value
    if kind == 'dozen':
        return number > 0 and (number - 1) // 12 + 1 == value
    if kind == 'column':
        return number > 0 and (number - 1) % 3 + 1 == value
    return {
        'red': number in RED_NUMBERS,
        'black': number > 0 and number not in RED_NUMBERS,
        'odd': number % 2 == 1,
        'even': number > 0 and number % 2 == 0,
        'low': 1 <= number <= 18,
        'high': 19 <= number <= 36,
    }[kind]


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


class RouletteTableRules(RouletteRules):
    """Version 2: one spin settles chips on several spots. Each bet in the selection carries its own stake."""

    def normalize_selection(self, selection):
        if (
            not isinstance(selection, dict)
            or set(selection) != {'bets'}
            or not isinstance(selection['bets'], list)
            or not selection['bets']
        ):
            raise ValueError('Place at least one roulette bet.')
        bets = {}
        for bet in selection['bets']:
            if not isinstance(bet, dict) or type(bet.get('amount')) is not int or bet['amount'] < 1:
                raise ValueError('Each roulette bet needs a whole stake of at least 1 TNB.')
            spot = super().normalize_selection({key: value for key, value in bet.items() if key != 'amount'})
            key = (TYPE_ORDER[spot['type']], spot.get('value', 0))
            if key in bets:
                raise ValueError('Each roulette spot can hold one bet.')
            bets[key] = {**spot, 'amount': bet['amount']}
        # Table order, so the same chips always make the same receipt whatever order they were placed in.
        return {'bets': [bets[key] for key in sorted(bets)]}

    def prepare_selection(self, selection, amount):
        if isinstance(selection, dict) and 'bets' not in selection:
            # A table that predates version 2 sends a single spot and stakes the whole wager on it.
            selection = {'bets': [{**selection, 'amount': amount}]}
        selection = self.normalize_selection(selection)
        if sum(bet['amount'] for bet in selection['bets']) != amount:
            raise ValueError('The roulette bets must add up to the wager.')
        return selection

    def returned(self, selection, number):
        """Total paid for a number, including the stakes of the winning bets."""
        return sum(
            bet['amount'] * ROULETTE_TYPES[bet['type']][1]
            for bet in selection['bets']
            if spot_wins(bet['type'], bet.get('value'), number)
        )

    def multiplier(self, selection):
        return max(ROULETTE_TYPES[bet['type']][1] for bet in selection['bets'])

    def exposure(self, selection, amount):
        # Bets that cover each other reduce what the casino can lose; a fully hedged table risks nothing.
        return max(0, max(self.returned(selection, number) for number in range(37)) - amount)

    def payout(self, amount, result):
        return result['payout']

    def outcome(self, random, selection):
        number = random.below(37)
        return {'number': number, 'color': pocket_color(number), 'payout': self.returned(selection, number)}

    def catalog_data(self, maximum_bet):
        return {**super().catalog_data(maximum_bet), 'multiple_bets': True}

    def verify(self):
        super().verify()
        for kind, (_, multiplier) in ROULETTE_TYPES.items():
            for value in {'number': range(37), 'dozen': range(1, 4), 'column': range(1, 4)}.get(kind, [None]):
                bet = {'type': kind, 'amount': 1} if value is None else {'type': kind, 'value': value, 'amount': 1}
                selection = self.prepare_selection({'bets': [bet]}, 1)
                if sum(self.returned(selection, number) for number in range(37)) != 36:
                    raise ValueError('Every roulette spot must return 36/37 of its stakes.')
                if self.exposure(selection, 1) != multiplier - 1:
                    raise ValueError('A single roulette bet must risk its multiplier less the stake.')
        every_number = self.prepare_selection(
            {'bets': [{'type': 'number', 'value': value, 'amount': 1} for value in range(37)]}, 37
        )
        if any(self.returned(every_number, number) != 36 for number in range(37)) or self.exposure(every_number, 37):
            raise ValueError('Covering every number must return 36 of 37 chips and risk nothing.')


ROULETTE_V1 = RouletteRules(
    game='roulette', version=1, name='Roulette', max_multiplier=36, house_edge=1 / 37, catalog_multiplier=2
)
ROULETTE_V2 = RouletteTableRules(
    game='roulette', version=2, name='Roulette', max_multiplier=36, house_edge=1 / 37, catalog_multiplier=2
)
