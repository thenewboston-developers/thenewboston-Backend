from django.utils import timezone

from ..enums import MatchEventType, MatchStatus
from ..models import ConnectFiveEscrow, ConnectFiveMatchEvent
from ..services.elo import apply_match_result
from ..services.escrow import get_wallet_for_update, settle_win


def finish_match_connect5(*, match, winner):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    winner_wallet = get_wallet_for_update(user=winner, currency=match.challenge.currency)
    settle_win(escrow=escrow, wallet=winner_wallet, amount=escrow.total)
    rating_snapshot = _apply_match_elo(match=match, winner=winner)
    match.status = MatchStatus.FINISHED_CONNECT5
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    if rating_snapshot:
        match.player_a_elo_before = rating_snapshot['player_a']['before']
        match.player_a_elo_after = rating_snapshot['player_a']['after']
        match.player_b_elo_before = rating_snapshot['player_b']['before']
        match.player_b_elo_after = rating_snapshot['player_b']['after']
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'player_a_elo_after',
            'player_a_elo_before',
            'player_b_elo_after',
            'player_b_elo_before',
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
    rating_snapshot = _apply_match_elo(match=match, winner=winner)
    match.status = MatchStatus.FINISHED_TIMEOUT
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    if rating_snapshot:
        match.player_a_elo_before = rating_snapshot['player_a']['before']
        match.player_a_elo_after = rating_snapshot['player_a']['after']
        match.player_b_elo_before = rating_snapshot['player_b']['before']
        match.player_b_elo_after = rating_snapshot['player_b']['after']
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'player_a_elo_after',
            'player_a_elo_before',
            'player_b_elo_after',
            'player_b_elo_before',
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


def finish_match_resign(*, match, resigning_player, winner):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    winner_wallet = get_wallet_for_update(user=winner, currency=match.challenge.currency)
    settle_win(escrow=escrow, wallet=winner_wallet, amount=escrow.total)
    rating_snapshot = _apply_match_elo(match=match, winner=winner)
    match.status = MatchStatus.FINISHED_RESIGN
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    if rating_snapshot:
        match.player_a_elo_before = rating_snapshot['player_a']['before']
        match.player_a_elo_after = rating_snapshot['player_a']['after']
        match.player_b_elo_before = rating_snapshot['player_b']['before']
        match.player_b_elo_after = rating_snapshot['player_b']['after']
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'player_a_elo_after',
            'player_a_elo_before',
            'player_b_elo_after',
            'player_b_elo_before',
            'prize_pool_total',
            'status',
            'winner',
        ],
    )

    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor=resigning_player,
        event_type=MatchEventType.RESIGN,
        payload={'winner_id': winner.id},
    )

    return now


def finish_match_full_board(*, match, winner):
    now = timezone.now()
    escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)
    winner_wallet = get_wallet_for_update(user=winner, currency=match.challenge.currency)
    settle_win(escrow=escrow, wallet=winner_wallet, amount=escrow.total)
    rating_snapshot = _apply_match_elo(match=match, winner=winner)
    match.status = MatchStatus.FINISHED_FULL_BOARD
    match.winner = winner
    match.finished_at = now
    match.prize_pool_total = escrow.total
    if rating_snapshot:
        match.player_a_elo_before = rating_snapshot['player_a']['before']
        match.player_a_elo_after = rating_snapshot['player_a']['after']
        match.player_b_elo_before = rating_snapshot['player_b']['before']
        match.player_b_elo_after = rating_snapshot['player_b']['after']
    match.save(
        update_fields=[
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'finished_at',
            'modified_date',
            'player_a_elo_after',
            'player_a_elo_before',
            'player_b_elo_after',
            'player_b_elo_before',
            'prize_pool_total',
            'status',
            'winner',
        ],
    )

    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor=winner,
        event_type=MatchEventType.SETTLEMENT,
        payload={'reason': MatchStatus.FINISHED_FULL_BOARD},
    )

    return now


def _apply_match_elo(*, match, winner):
    if match.player_a_elo_after is not None or match.player_b_elo_after is not None:
        return None

    return apply_match_result(match=match, winner=winner)
