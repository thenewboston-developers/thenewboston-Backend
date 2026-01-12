from django.utils import timezone

from ..enums import MatchEventType, MatchStatus
from ..models import ConnectFiveEscrow, ConnectFiveMatchEvent
from ..services.escrow import get_wallet_for_update, settle_draw, settle_win


def finish_match_connect5(*, match, winner):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    winner_wallet = get_wallet_for_update(user=winner, currency=match.challenge.currency)
    settle_win(escrow=escrow, wallet=winner_wallet, amount=escrow.total)
    match.status = MatchStatus.FINISHED_CONNECT5
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'prize_pool_total',
            'status',
            'winner',
        ],
    )

    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor=winner,
        event_type=MatchEventType.SETTLEMENT,
        payload={'reason': MatchStatus.FINISHED_CONNECT5},
    )

    return now


def finish_match_timeout(*, match, winner):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    winner_wallet = get_wallet_for_update(user=winner, currency=match.challenge.currency)
    settle_win(escrow=escrow, wallet=winner_wallet, amount=escrow.total)
    match.status = MatchStatus.FINISHED_TIMEOUT
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'prize_pool_total',
            'status',
            'winner',
        ],
    )

    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor=None,
        event_type=MatchEventType.TIMEOUT,
        payload={'winner_id': winner.id},
    )

    return now


def finish_match_draw(*, match):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    wallet_a = get_wallet_for_update(user=match.player_a, currency=match.challenge.currency)
    wallet_b = get_wallet_for_update(user=match.player_b, currency=match.challenge.currency)
    settle_draw(escrow=escrow, wallet_a=wallet_a, wallet_b=wallet_b)
    match.status = MatchStatus.DRAW
    match.finished_at = now
    match.prize_pool_total = escrow.total
    match.save(
        update_fields=['finished_at', 'modified_date', 'prize_pool_total', 'status'],
    )

    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor=None,
        event_type=MatchEventType.SETTLEMENT,
        payload={'reason': MatchStatus.DRAW},
    )

    return now
