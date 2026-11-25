from datetime import timedelta

from thenewboston.casino.contracts import GameRules

from . import engine

OPTIMAL_RETURN = engine.OPTIMAL_RETURN[0] / engine.OPTIMAL_RETURN[1]


class VideoPokerRules(GameRules):
    def normalize_selection(self, selection):
        if selection not in (None, {}):
            raise ValueError('Video Poker does not accept a selection.')
        return {}

    def multiplier(self, selection):
        return engine.MAX_MULTIPLIER

    def outcome(self, random, selection):
        return engine.initial_state(engine.shuffled_deck(random))

    def public_result(self, bet):
        # The stored state never contains undealt cards; the rest of the shuffle exists only behind the seed.
        state = bet.result
        result = {key: state[key] for key in ('dealt', 'hand', 'held', 'phase', 'category', 'revision')}
        is_open = bet.status == 'open'
        result['available_actions'] = engine.available_actions(state) if is_open else []
        result['expires_at'] = (
            (bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS)).isoformat() if is_open else None
        )
        if not is_open:
            result.update({key: state[key] for key in ('actions', 'multiplier')})
        return result

    def start_bet(self, *, fund, bet, wallet):
        from .services import verify_deal

        verify_deal(bet)

    def act(self, **kwargs):
        from .services import act

        return act(**kwargs)

    def catalog_data(self, maximum_bet):
        return {
            'variant': 'jacks_or_better',
            'decks': 1,
            'pay_table': [
                {'hand': hand, 'name': name, 'multiplier': multiplier} for hand, name, multiplier in engine.PAY_TABLE
            ],
            'optimal_return': OPTIMAL_RETURN,
            'house_edge_note': 'With perfect play. Your return depends on the cards you hold.',
            'timeout_seconds': engine.TIMEOUT_SECONDS,
            'rules': [
                'One 52-card deck is freshly shuffled for every hand.',
                'Five cards are dealt. Hold any of them, then draw once to replace the rest.',
                'A pair of jacks, queens, kings or aces returns your wager. Better hands pay more.',
                'Payouts are total returns, wager included: a royal flush returns 250 times the wager.',
                'A hand left open is drawn with all five cards held 15 minutes after the deal.',
            ],
        }

    def verify(self):
        if [multiplier for _, _, multiplier in engine.PAY_TABLE] != [250, 50, 25, 9, 6, 4, 3, 2, 1]:
            raise ValueError('Video Poker must use the 9/6 Jacks or Better pay table.')
        if not (self.multiplier({}) == self.max_multiplier == self.catalog_multiplier == engine.MAX_MULTIPLIER == 250):
            raise ValueError('Video Poker maximum exposure must cover a royal flush.')
        if engine.hand_counts() != engine.HAND_COUNTS or sum(engine.HAND_COUNTS.values()) != 2598960:
            raise ValueError('Video Poker hand evaluation failed.')
        if engine.evaluate(['10S', 'JS', 'QS', 'KS', 'AS']) != 'royal_flush' or engine.evaluate(
            ['10S', '10H', '4D', '7C', '2S']
        ) != ('nothing'):
            raise ValueError('Video Poker hand evaluation failed.')
        if self.house_edge != 1 - OPTIMAL_RETURN or not 0.98 < OPTIMAL_RETURN < 0.99:
            raise ValueError('Video Poker house edge does not match its published optimal return.')


VIDEO_POKER_V1 = VideoPokerRules(
    game='video_poker',
    version=1,
    name='Video Poker',
    max_multiplier=engine.MAX_MULTIPLIER,
    house_edge=1 - OPTIMAL_RETURN,
    catalog_multiplier=engine.MAX_MULTIPLIER,
    settlement_mode='interactive',
)
