"""Independent games, administrator rosters, and committed scheduling boundaries."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker
from rest_framework.exceptions import PermissionDenied, ValidationError

from thenewboston.tribes import services
from thenewboston.tribes.models import Tournament, TournamentParticipant

from .test_integrity import action, client_for, snapshot

pytestmark = pytest.mark.django_db(transaction=True)


def another_tournament(game, *, max_players=12):
    tournament = services.create_tournament(
        title='Independent tournament',
        starts_at=timezone.now() + timedelta(days=1),
        max_players=max_players,
        actor=game['admin'],
    )
    for name in ('alice', 'bob'):
        user_id = game[f'{name}_wallet'].owner_id
        services.add_participant(tournament.pk, user_id, actor=game['admin'])
        services.create_tribe(tournament.pk, name=f'{name} second tribe', founder_id=user_id, actor=game['admin'])
    return tournament


def activate(tournament):
    tournament.starts_at = timezone.now() - timedelta(seconds=1)
    tournament.ends_at = tournament.starts_at + timedelta(days=7)
    tournament.save(update_fields=['starts_at', 'ends_at'])
    services.advance_tournament(tournament.pk)
    tournament.refresh_from_db()


def test_public_directory_does_not_create_a_game_and_selection_is_required():
    client = client_for()
    assert client.get('/api/tribes/tournaments').data == []
    assert client.get('/api/tribes/state').status_code == 400
    assert client.get('/api/tribes/state', {'tournament_id': 'invalid'}).status_code == 400
    assert client.get('/api/tribes/state', {'tournament_id': 999}).status_code == 404
    assert not Tournament.objects.exists()
    assert client.post('/api/tribes/tournaments', {}, format='json').status_code == 405


def test_public_directory_metadata_and_unassigned_participant(tribes_game):
    game = tribes_game
    tournament = game['tournament']
    member = baker.make('users.User')
    services.add_participant(tournament.pk, member.pk, actor=game['admin'])
    public = client_for().get('/api/tribes/tournaments').data[0]
    assert public == {
        'id': tournament.pk,
        'title': 'Test tournament',
        'status': 'upcoming',
        'starts_at': tournament.starts_at.isoformat(),
        'ends_at': tournament.ends_at.isoformat(),
        'max_players': 12,
        'player_count': 3,
        'is_participant': False,
    }
    state = snapshot(client_for(member), tournament)
    assert state['tournament']['is_participant'] is True
    assert state['viewer']['is_participant'] is True
    assert state['viewer']['tribe_id'] is None
    assert all(tribe['treasury'] is None for tribe in state['tribes'])
    action(client_for(member), tournament, 'message', text='No tribe', expected=400)


def test_only_admin_with_permission_can_create_and_manage_tournaments(tribes_game):
    game = tribes_game
    outsider = baker.make('users.User', is_staff=True, is_superuser=False)
    with pytest.raises(PermissionDenied):
        services.create_tournament(
            title='Unauthorized', starts_at=timezone.now() + timedelta(days=1), max_players=12, actor=outsider
        )
    with pytest.raises(PermissionDenied):
        services.add_participant(game['tournament'].pk, outsider.pk, actor=game['alice_wallet'].owner)
    action(client_for(outsider), game['tournament'], 'create_tribe', name='Bypass', expected=403)
    action(game['alice'], game['tournament'], 'create_tribe', name='Bypass', expected=400)
    assert Tournament.objects.count() == 1


def test_capacity_enrollment_idempotency_and_one_tribe_per_tournament(tribes_game):
    game = tribes_game
    tournament = game['tournament']
    services.update_tournament(
        tournament.pk, title=tournament.title, starts_at=tournament.starts_at, max_players=2, actor=game['admin']
    )
    services.add_participant(tournament.pk, game['alice_wallet'].owner_id, actor=game['admin'])
    with pytest.raises(ValidationError, match='full'):
        services.add_participant(tournament.pk, baker.make('users.User').pk, actor=game['admin'])
    with pytest.raises(ValidationError, match='lower'):
        services.update_tournament(
            tournament.pk, title=tournament.title, starts_at=tournament.starts_at, max_players=1, actor=game['admin']
        )
    with pytest.raises(ValidationError, match='already belongs'):
        services.create_tribe(
            tournament.pk, name='Duplicate membership', founder_id=game['alice_wallet'].owner_id, actor=game['admin']
        )
    assert tournament.participants.count() == 2


def test_captain_transfer_required_before_moving_member(tribes_game):
    game = tribes_game
    tournament = game['tournament']
    member = baker.make('users.User')
    services.add_participant(tournament.pk, member.pk, actor=game['admin'])
    services.assign_participant(tournament.pk, member.pk, game['alice_tribe'], actor=game['admin'])
    with pytest.raises(ValidationError, match='replacement captain'):
        services.assign_participant(
            tournament.pk, game['alice_wallet'].owner_id, game['bob_tribe'], actor=game['admin']
        )
    services.set_tribe_captain(tournament.pk, game['alice_tribe'], member.pk, actor=game['admin'])
    services.assign_participant(tournament.pk, game['alice_wallet'].owner_id, game['bob_tribe'], actor=game['admin'])
    state = snapshot(game['alice'], tournament)
    assert state['viewer']['tribe_id'] == game['bob_tribe']
    assert sum(m['id'] == game['alice_wallet'].owner_id for t in state['tribes'] for m in t['members']) == 1


def test_roster_and_schedule_are_frozen_after_start(active_game):
    game = active_game
    tournament = game['tournament']
    with pytest.raises(ValidationError, match='locked'):
        services.remove_participant(tournament.pk, game['alice_wallet'].owner_id, actor=game['admin'])
    with pytest.raises(ValidationError, match='locked'):
        services.update_tournament(
            tournament.pk,
            title='Changed',
            starts_at=timezone.now() + timedelta(days=2),
            max_players=20,
            actor=game['admin'],
        )
    tournament.refresh_from_db()
    assert tournament.title == 'Test tournament'
    assert tournament.participants.count() == 2


def test_same_user_plays_two_games_without_sharing_state(active_game):
    game = active_game
    first, second = game['tournament'], another_tournament(game)
    activate(second)
    action(game['alice'], first, 'treasury_deposit', amount=100)
    action(game['alice'], first, 'message', text='First game only')
    own_plot = next(p for p in snapshot(game['alice'], first)['plots'] if p['tribe_id'] == game['alice_tribe'])
    action(game['alice'], first, 'queue', kind='gather', plot_id=own_plot['id'], hours=1)
    other = snapshot(game['alice'], second)
    assert other['viewer']['is_participant'] is True
    assert other['viewer']['tribe_id'] is not None
    assert other['viewer']['wallet_balance'] == 900
    assert other['viewer']['inventory'] == {}
    assert other['messages'] == []
    assert other['jobs'] == []
    assert next(t for t in other['tribes'] if t['id'] == other['viewer']['tribe_id'])['treasury'] == 0
    second.refresh_from_db()
    assert second.total_deposited == 0
    assert TournamentParticipant.objects.filter(user_id=game['alice_wallet'].owner_id).count() == 2


def test_request_ids_are_scoped_to_selected_tournament(active_game):
    game = active_game
    second = another_tournament(game)
    activate(second)
    request_id = uuid4()
    action(game['alice'], game['tournament'], 'treasury_deposit', amount=100, request_id=request_id)
    action(game['alice'], second, 'treasury_deposit', amount=200, request_id=request_id)
    action(game['alice'], second, 'treasury_deposit', amount=200, request_id=request_id)
    game['alice_wallet'].refresh_from_db()
    assert game['alice_wallet'].balance == 700


def test_sweep_advances_each_game_and_isolates_failures(tribes_game, monkeypatch):
    game = tribes_game
    first, second = game['tournament'], another_tournament(game)
    advance = services._advance

    def fail_one(tournament, now):
        if tournament.pk == first.pk:
            raise RuntimeError('Broken isolated game')
        return advance(tournament, now)

    monkeypatch.setattr(services, '_advance', fail_one)
    with freeze_time(second.starts_at + timedelta(seconds=1)):
        result = services.sweep_tournaments()
    assert result == {'processed': [second.pk], 'failed': [first.pk]}
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == 'upcoming'
    assert second.status == 'active'
    assert Tournament.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_rejected_http_action_still_commits_due_finish_and_refunds(active_game):
    game = active_game
    tournament = game['tournament']
    action(game['alice'], tournament, 'treasury_deposit', amount=500)
    with freeze_time(tournament.ends_at):
        action(game['alice'], tournament, 'treasury_deposit', amount=1, expected=400)
    tournament.refresh_from_db()
    game['alice_wallet'].refresh_from_db()
    assert tournament.status == 'finished'
    assert tournament.state['battle'] is not None
    assert game['alice_wallet'].balance == 1000
    assert tournament.money_entries.filter(reason='tournament_refund').count() == 1
    assert Tournament.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_rejected_http_action_still_commits_due_start(tribes_game):
    game = tribes_game
    tournament = game['tournament']
    with freeze_time(tournament.starts_at):
        action(game['alice'], tournament, 'unknown', expected=400)
    tournament.refresh_from_db()
    assert tournament.status == 'active'
    assert tournament.state['plots']
