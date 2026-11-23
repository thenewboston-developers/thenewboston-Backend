from django.db import transaction
from django.utils import timezone

from thenewboston.project.celery import app

from .models import BackgammonMatch
from .services import apply_clock, expire_match, queue_computer, run_computer, start_next_game


@app.task(name='tasks.play_backgammon_computer_turn', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def play_computer_turn(match_id, expected_version):
    run_computer(match_id, expected_version)


@app.task(name='tasks.sweep_backgammon_matches')
def sweep_backgammon_matches():
    # The periodic sweep also recovers CPU turns whose original queue delivery failed.
    ids = BackgammonMatch.objects.filter(status__in=['pending', 'active', 'between_games']).values_list('id', flat=True)
    for match_id in ids.iterator():
        with transaction.atomic():
            match = BackgammonMatch.objects.select_for_update().get(pk=match_id)
            if match.status == 'between_games' and match.next_game_at <= timezone.now():
                start_next_game(match)
            if not expire_match(match) and not apply_clock(match):
                queue_computer(match)
