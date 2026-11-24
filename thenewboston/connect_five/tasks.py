from django.db import transaction
from django.utils import timezone

from thenewboston.project.celery import app

from .enums import ChallengeStatus, MatchStatus
from .models import ConnectFiveChallenge, ConnectFiveEloSnapshot, ConnectFiveEscrow, ConnectFiveMatch, ConnectFiveStats
from .services.clocks import apply_elapsed_time
from .services.computer import expire_computer_match, queue_computer_turn, run_computer_turn
from .services.escrow import get_wallet_for_update, refund_challenge
from .services.match import finish_match_timeout
from .services.streaming import stream_challenge_update, stream_match_update


@app.task(name='tasks.expire_connect_five_challenges')
def expire_connect_five_challenges_task():
    now = timezone.now()
    challenge_ids = (
        ConnectFiveChallenge.objects.filter(
            status=ChallengeStatus.PENDING,
            expires_at__lte=now,
            rematch_for__isnull=True,
        )
        .values_list('id', flat=True)
        .order_by('id')
    )

    for challenge_id in challenge_ids:
        with transaction.atomic():
            challenge = (
                ConnectFiveChallenge.objects.select_for_update()
                .select_related('challenger', 'currency')
                .get(pk=challenge_id)
            )
            escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=challenge)
            if challenge.status != ChallengeStatus.PENDING or challenge.expires_at > now:
                continue

            challenge.status = ChallengeStatus.EXPIRED
            challenge.save(update_fields=['status', 'modified_date'])

            wallet = get_wallet_for_update(user=challenge.challenger, currency=challenge.currency)
            refund_challenge(escrow=escrow, wallet=wallet)
            stream_challenge_update(challenge=challenge)


@app.task(name='tasks.sweep_connect_five_timeouts')
def sweep_connect_five_timeouts_task():
    match_ids = ConnectFiveMatch.objects.filter(status=MatchStatus.ACTIVE).values_list('id', flat=True).order_by('id')

    for match_id in match_ids:
        with transaction.atomic():
            match = (
                ConnectFiveMatch.objects.select_for_update(of=('self',))
                .select_related('challenge', 'player_a', 'player_b')
                .get(pk=match_id)
            )
            if match.status != MatchStatus.ACTIVE:
                continue

            if match.mode == 'computer':
                if not expire_computer_match(match):
                    queue_computer_turn(match)
                continue

            remaining, _ = apply_elapsed_time(match)
            if remaining > 0:
                continue

            winner = match.player_b if match.active_player_id == match.player_a_id else match.player_a
            finish_match_timeout(match=match, winner=winner)
            stream_match_update(match=match)


@app.task(name='tasks.capture_connect_five_elo_snapshots')
def capture_connect_five_elo_snapshots_task():
    snapshot_date = timezone.localdate()
    stats_queryset = ConnectFiveStats.objects.all().only('elo', 'user_id')

    for stats in stats_queryset.iterator():
        ConnectFiveEloSnapshot.objects.update_or_create(
            user_id=stats.user_id,
            snapshot_date=snapshot_date,
            defaults={'elo': stats.elo},
        )


@app.task(name='tasks.play_connect_five_computer_turn', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def play_connect_five_computer_turn(match_id, expected_version):
    run_computer_turn(match_id, expected_version)
