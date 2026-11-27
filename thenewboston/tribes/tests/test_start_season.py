from copy import deepcopy
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from freezegun import freeze_time

from thenewboston.tribes.management.commands import start_tribes_season
from thenewboston.tribes.models import Activity, Season
from thenewboston.tribes.services import new_state

from .test_integrity import action, snapshot

pytestmark = pytest.mark.django_db


def start(season_id):
    output = StringIO()
    call_command('start_tribes_season', season_id=season_id, stdout=output)
    return output.getvalue()


def test_start_solo_season_preserves_duration_and_initializes_play(tribes_game):
    game = tribes_game
    season = game['season']
    action(game['bob'], season, 'leave')
    season.refresh_from_db()
    duration = season.ends_at - season.starts_at
    now = timezone.now()
    with freeze_time(now):
        assert f'Started Tribes season {season.pk}' in start(season.pk)
        state = snapshot(game['alice'], season)
        assert state['season']['status'] == 'active'
        assert len(state['tribes']) == 1
        assert len(state['plots']) == 25
        assert len(state['listings']) == 6
        home = next(plot for plot in state['plots'] if plot['tribe_id'] == game['alice_tribe'])
        action(game['alice'], season, 'queue', kind='gather', plot_id=home['id'], hours=1)
        action(game['alice'], season, 'leave', expected=400)
    season.refresh_from_db()
    assert season.starts_at == now
    assert season.ends_at == now + duration
    assert season.money_entries.count() == 0
    game['alice_wallet'].refresh_from_db()
    assert game['alice_wallet'].balance == 1000


def test_retry_does_not_reset_active_schedule_or_gameplay(active_game):
    season = active_game['season']
    before = deepcopy(season.state)
    original_start, original_end = season.starts_at, season.ends_at
    activities = Activity.objects.filter(season=season).count()
    with freeze_time(original_start + timedelta(hours=2)):
        assert 'already active' in start(season.pk)
    season.refresh_from_db()
    assert (season.starts_at, season.ends_at) == (original_start, original_end)
    assert season.state == before
    assert Activity.objects.filter(season=season).count() == activities


def test_due_season_keeps_existing_deadline(tribes_game):
    season = tribes_game['season']
    original_start, original_end = season.starts_at, season.ends_at
    with freeze_time(original_start + timedelta(hours=1)):
        start(season.pk)
    season.refresh_from_db()
    assert season.status == 'active'
    assert (season.starts_at, season.ends_at) == (original_start, original_end)


def test_rejects_missing_season_without_creating_one():
    with pytest.raises(CommandError, match='not the current'):
        start(1)
    assert not Season.objects.exists()


def test_rejects_stale_season_without_starting_next(tribes_game):
    season = tribes_game['season']
    newer = Season.objects.create(starts_at=season.starts_at, ends_at=season.ends_at, state=new_state())
    with pytest.raises(CommandError, match='not the current'):
        start(season.pk)
    season.refresh_from_db()
    newer.refresh_from_db()
    assert season.status == newer.status == 'recruiting'


@pytest.mark.parametrize('status', ['recruiting', 'active', 'finished'])
def test_rejects_expired_season_without_rescheduling(tribes_game, status):
    season = tribes_game['season']
    season.status = status
    season.save(update_fields=['status'])
    original_start, original_end = season.starts_at, season.ends_at
    with freeze_time(original_end), pytest.raises(CommandError, match='has ended'):
        start(season.pk)
    season.refresh_from_db()
    assert season.status == status
    assert (season.starts_at, season.ends_at) == (original_start, original_end)


@pytest.mark.parametrize('empty_tribe', [False, True])
def test_rejects_empty_roster(tribes_game, empty_tribe):
    season = tribes_game['season']
    season.refresh_from_db()
    if empty_tribe:
        season.state['tribes'][0]['members'] = []
    else:
        season.state['tribes'] = []
    season.save(update_fields=['state'])
    with pytest.raises(CommandError, match='at least one tribe'):
        start(season.pk)
    season.refresh_from_db()
    assert season.status == 'recruiting'
    assert not season.state['plots']


def test_rejects_partially_initialized_recruiting_season(tribes_game):
    season = tribes_game['season']
    season.refresh_from_db()
    season.state['plots'] = [{'id': 1}]
    season.save(update_fields=['state'])
    with pytest.raises(CommandError, match='already contains gameplay'):
        start(season.pk)
    season.refresh_from_db()
    assert season.status == 'recruiting'
    assert season.state['plots'] == [{'id': 1}]


def test_start_failure_rolls_back_schedule_state_and_activity(tribes_game, monkeypatch):
    season = tribes_game['season']
    season.refresh_from_db()
    before = deepcopy(season.state)
    original_start, original_end = season.starts_at, season.ends_at
    activities = Activity.objects.filter(season=season).count()
    advance = start_tribes_season._advance

    def fail_after_start(season, now):
        advance(season, now)
        raise RuntimeError('Simulated failure')

    monkeypatch.setattr(start_tribes_season, '_advance', fail_after_start)
    with pytest.raises(RuntimeError, match='Simulated failure'):
        start(season.pk)
    season.refresh_from_db()
    assert season.status == 'recruiting'
    assert (season.starts_at, season.ends_at) == (original_start, original_end)
    assert season.state == before
    assert Activity.objects.filter(season=season).count() == activities
