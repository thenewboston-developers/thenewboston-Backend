"""Let It Ride rules. Preserve every installed version's deal, paytable and state for replaying historical receipts."""

from datetime import timedelta

from thenewboston.casino.contracts import GameRules

from . import engine

# Exact expected loss with the best decisions on every hand, as a share of one of the three bets.
OPTIMAL_EDGE_PER_BET = 7979 / 249900


class LetItRideRules(GameRules):
    def normalize_selection(self, selection):
        if selection not in (None, {}):
            raise ValueError('Let It Ride does not accept a selection.')
        return {}

    def validate_amount(self, amount):
        if amount % engine.BETS:
            raise ValueError('Let It Ride takes three equal bets, so the wager must be a multiple of 3 TNB.')

    def minimum_bet(self, configured):
        # The first amount at or above the configured minimum that splits into three equal bets.
        return max(engine.BETS, -(-configured // engine.BETS) * engine.BETS)

    def multiplier(self, selection):
        # Worst case for the casino: all three bets ride and the hand is a royal flush.
        return engine.MAX_ODDS + 1

    def outcome(self, random, selection):
        return engine.initial_state(*engine.deal(random))

    def public_result(self, bet):
        """The hand as the player may see it: a community card stays hidden until the decision before it is made."""
        state = bet.result
        settled = bet.status == 'settled'
        result = {key: state[key] for key in ('cards', 'decisions', 'revision', 'phase', 'riding', 'hand', 'odds')}
        turned = state['community'][: len(state['decisions'])]
        result['community'] = state['community'] if settled else [*turned, None, None][:2]
        result['available_actions'] = [] if settled else list(engine.ACTIONS)
        result['expires_at'] = (
            None if settled else (bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS)).isoformat()
        )
        return result

    def start_bet(self, *, fund, bet, wallet):
        """The deal settles nothing: the hand stays open until both decisions are made or it times out."""

    def act(self, **kwargs):
        from .services import act

        return act(**kwargs)

    def catalog_data(self, maximum_bet):
        return {
            'max_bet': maximum_bet(self.catalog_multiplier) // engine.BETS * engine.BETS,
            'bet_increment': engine.BETS,
            'bets': engine.BETS,
            'paytable': [{'hand': hand, 'odds': odds} for hand, odds in engine.PAYTABLE],
            'house_edge_per_bet': OPTIMAL_EDGE_PER_BET,
            'timeout_seconds': engine.TIMEOUT_SECONDS,
        }

    def verify(self):
        if dict(engine.PAYTABLE) != {
            'royal_flush': 100,
            'straight_flush': 50,
            'four_of_a_kind': 25,
            'full_house': 15,
            'flush': 10,
            'straight': 6,
            'three_of_a_kind': 3,
            'two_pair': 2,
            'tens_or_better': 1,
        }:
            raise ValueError('The Let It Ride paytable changed.')
        if not self.multiplier({}) == self.max_multiplier == self.catalog_multiplier == engine.MAX_ODDS + 1 == 101:
            raise ValueError('Let It Ride exposure must cover three riding bets on a royal flush.')
        if len(set(engine.DECK)) != 52 or engine.BETS != 3:
            raise ValueError('Let It Ride needs one 52-card deck and three bets.')
        samples = {
            ('TS', 'JS', 'QS', 'KS', 'AS'): 'royal_flush',
            ('AD', '2D', '3D', '4D', '5D'): 'straight_flush',
            ('9C', '9D', '9H', '9S', '2C'): 'four_of_a_kind',
            ('3C', '3D', '3H', 'KS', 'KC'): 'full_house',
            ('2H', '7H', '9H', 'JH', 'KH'): 'flush',
            ('AC', '2D', '3H', '4S', '5C'): 'straight',
            ('TC', 'JD', 'QH', 'KS', 'AC'): 'straight',
            ('7C', '7D', '7H', 'KS', '2C'): 'three_of_a_kind',
            ('4C', '4D', 'JH', 'JS', 'AC'): 'two_pair',
            ('TC', 'TD', '2H', '5S', '9C'): 'tens_or_better',
            ('9C', '9D', '2H', '5S', 'AC'): engine.NO_WIN,
            ('JC', 'QD', 'KH', 'AS', '2C'): engine.NO_WIN,
        }
        if any(engine.rank_hand(list(cards)) != hand for cards, hand in samples.items()):
            raise ValueError('Let It Ride hand ranking failed.')
        if self.house_edge != OPTIMAL_EDGE_PER_BET / engine.BETS:
            raise ValueError('The Let It Ride house edge does not match its paytable.')


LET_IT_RIDE_V1 = LetItRideRules(
    game='let_it_ride',
    version=1,
    name='Let It Ride',
    max_multiplier=101,
    # Expected loss with the best decisions, as a share of the three bets staked at the deal.
    house_edge=OPTIMAL_EDGE_PER_BET / engine.BETS,
    catalog_multiplier=101,
    settlement_mode='interactive',
)
