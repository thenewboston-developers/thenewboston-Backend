from datetime import timedelta

from thenewboston.casino.contracts import GameRules

from . import engine


class BlackjackRules(GameRules):
    def normalize_selection(self, selection):
        if selection not in (None, {}):
            raise ValueError('Blackjack does not accept a selection.')
        return {}

    def validate_amount(self, amount):
        if amount % 2:
            raise ValueError('Blackjack wagers must be even whole amounts so 3:2 payouts remain whole TNB.')

    def multiplier(self, selection):
        # Net maximum exposure is twice the INITIAL stake: a double returns four stakes after two were paid.
        return 3

    def minimum_bet(self, configured):
        return max(2, configured + configured % 2)

    def outcome(self, random, selection):
        return engine.initial_state(engine.shuffled_deck(random))

    def public_result(self, bet):
        state = bet.result
        result = {key: state[key] for key in ('player_cards', 'player_total', 'phase', 'outcome', 'revision')}
        result['available_actions'] = engine.available_actions(state) if bet.status == 'open' else []
        result['expires_at'] = (
            (bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS)).isoformat() if bet.status == 'open' else None
        )
        if bet.status == 'open':
            result['dealer_cards'] = [state['dealer_cards'][0], None]
            result['dealer_total'] = engine.total(state['dealer_cards'][:1])
        else:
            result.update(
                {key: state[key] for key in ('dealer_cards', 'dealer_total', 'actions', 'multiplier', 'doubled')}
            )
        return result

    def start_bet(self, *, fund, bet, wallet):
        from .services import settle_initial

        settle_initial(fund=fund, bet=bet, wallet=wallet)

    def act(self, **kwargs):
        from .services import act

        return act(**kwargs)

    def catalog_data(self, maximum_bet):
        return {
            'max_bet': maximum_bet(3) // 2 * 2,
            'bet_increment': 2,
            'decks': engine.DECKS,
            'dealer_stands_on_soft_17': True,
            'blackjack_payout': '3:2',
            'timeout_seconds': engine.TIMEOUT_SECONDS,
            'house_edge': None,
            'house_edge_note': 'Return depends on player decisions.',
            'rules': [
                'Six decks are freshly shuffled for each hand.',
                'Blackjack pays 3:2. Other wins pay 1:1. Ties return your stake.',
                'The dealer checks for blackjack and stands on all 17s.',
                'Double on your first decision: add the original stake and receive exactly one card.',
                'No splitting, insurance or surrender.',
                'Hands automatically stand 15 minutes after the deal.',
            ],
        }

    def verify(self):
        if self.multiplier({}) != 3 or self.max_multiplier != 4 or self.catalog_multiplier != 3:
            raise ValueError('Blackjack maximum exposure must cover double down.')
        if engine.total(['AS', 'AH', '9D']) != 21 or engine.total(['AS', '6H']) != 17:
            raise ValueError('Blackjack ace evaluation failed.')
        if len(engine.RANKS) * len(engine.SUITS) * engine.DECKS != 312:
            raise ValueError('Blackjack requires six complete decks.')


BLACKJACK_V1 = BlackjackRules(
    game='blackjack',
    version=1,
    name='Blackjack',
    max_multiplier=4,
    house_edge=0,
    catalog_multiplier=3,
    settlement_mode='interactive',
)
