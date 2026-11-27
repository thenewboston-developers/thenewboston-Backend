from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker
from rest_framework.exceptions import ValidationError

from thenewboston.tribes import services
from thenewboston.tribes.models import Tournament, TournamentParticipant


@pytest.fixture
def tournament_admin():
    actor = baker.make('users.User', is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(actor)
    return client, actor


@pytest.fixture
def upcoming_tournament(tournament_admin):
    return services.create_tournament(
        title='Playtest cup', starts_at=timezone.now() + timedelta(days=2), max_players=12, actor=tournament_admin[1]
    )


def setup_payload(starts_at, **extra):
    local_start = timezone.localtime(starts_at)
    return {
        'title': 'November cup',
        'starts_at_0': local_start.strftime('%Y-%m-%d'),
        'starts_at_1': local_start.strftime('%H:%M:%S'),
        'ends_at_0': '',
        'ends_at_1': '',
        'max_players': '12',
        '_save': 'Save',
        **extra,
    }


def roster_action(client, tournament, operation, **values):
    return client.post(
        reverse('admin:tribes_tournament_roster', args=[tournament.pk]),
        {'operation': operation, **{f'{operation}-{name}': value for name, value in values.items()}},
    )


def test_create_tournament_initializes_game_and_defaults_duration(tournament_admin):
    client, actor = tournament_admin
    starts_at = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
    response = client.post(
        reverse('admin:tribes_tournament_add'),
        setup_payload(starts_at, state='{"tribes": ["forged"]}', status='finished', total_deposited='9000'),
    )
    assert response.status_code == 302
    tournament = Tournament.objects.get()
    assert tournament.starts_at == starts_at
    assert tournament.ends_at == starts_at + timedelta(days=7)
    assert tournament.status == 'upcoming'
    assert tournament.state == services.new_state()
    assert tournament.total_deposited == 0
    assert LogEntry.objects.filter(user=actor, object_id=str(tournament.pk), action_flag=ADDITION).exists()
    page = client.get(reverse('admin:tribes_tournament_change', args=[tournament.pk]))
    assert page.status_code == 200
    assert b'Manage roster' in page.content
    assert b'UTC' in page.content
    assert b'name="state"' not in page.content


def test_setup_rejects_invalid_dates_and_capacity(tournament_admin):
    client, _ = tournament_admin
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at - timedelta(days=1)
    response = client.post(
        reverse('admin:tribes_tournament_add'),
        setup_payload(
            starts_at,
            ends_at_0=ends_at.strftime('%Y-%m-%d'),
            ends_at_1=ends_at.strftime('%H:%M:%S'),
            max_players='0',
        ),
    )
    assert response.status_code == 200
    assert 'ends_at' in response.context['adminform'].form.errors
    assert 'max_players' in response.context['adminform'].form.errors
    assert not Tournament.objects.exists()


def test_staff_creation_and_roster_permissions_are_separate():
    actor = baker.make('users.User', is_staff=True)
    actor.user_permissions.add(Permission.objects.get(codename='add_tournament', content_type__app_label='tribes'))
    client = Client()
    client.force_login(actor)
    response = client.post(reverse('admin:tribes_tournament_add'), setup_payload(timezone.now() + timedelta(days=1)))
    assert response.status_code == 302
    tournament = Tournament.objects.get()
    player = baker.make('users.User', is_active=True)
    assert roster_action(client, tournament, 'enroll', username=player.username, tribe_id='').status_code == 403
    actor.user_permissions.add(Permission.objects.get(codename='change_tournament', content_type__app_label='tribes'))
    assert roster_action(client, tournament, 'enroll', username=player.username, tribe_id='').status_code == 302
    assert tournament.participants.filter(user=player).exists()


def test_settings_updates_preserve_rosters_and_validate_capacity(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    first, second = baker.make('users.User', is_active=True, _quantity=2)
    for user in (first, second):
        services.add_participant(upcoming_tournament.pk, user.pk, actor=actor)
    tournament = services.create_tribe(upcoming_tournament.pk, name='Oak', founder_id=first.pk, actor=actor)
    saved_state = tournament.state
    url = reverse('admin:tribes_tournament_change', args=[tournament.pk])
    response = client.post(url, setup_payload(tournament.starts_at, max_players='1'))
    assert response.status_code == 200
    assert 'max_players' in response.context['adminform'].form.errors
    end = timezone.localtime(tournament.starts_at + timedelta(days=3)).replace(microsecond=0)
    response = client.post(
        url,
        setup_payload(
            tournament.starts_at,
            title='Updated cup',
            max_players='8',
            ends_at_0=end.strftime('%Y-%m-%d'),
            ends_at_1=end.strftime('%H:%M:%S'),
            state='{}',
        ),
    )
    assert response.status_code == 302
    tournament.refresh_from_db()
    assert tournament.title == 'Updated cup'
    assert tournament.max_players == 8
    assert tournament.ends_at == end
    assert tournament.state == saved_state


def test_roster_workflow_and_admin_audit(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    first, second, third = baker.make('users.User', is_active=True, _quantity=3)
    tournament = upcoming_tournament
    for user in (first, second, third):
        assert roster_action(client, tournament, 'enroll', username=user.username, tribe_id='').status_code == 302
    assert roster_action(client, tournament, 'create_tribe', name='Oak', founder_id=first.pk).status_code == 302
    tournament.refresh_from_db()
    oak = tournament.state['tribes'][0]['id']
    assert roster_action(client, tournament, 'assign', user_id=second.pk, tribe_id=oak).status_code == 302
    assert roster_action(client, tournament, 'captain', user_id=second.pk, tribe_id=oak).status_code == 302
    assert roster_action(client, tournament, 'assign', user_id=first.pk, tribe_id='').status_code == 302
    assert roster_action(client, tournament, 'create_tribe', name='Pine', founder_id=first.pk).status_code == 302
    tournament.refresh_from_db()
    pine = tournament.state['tribes'][1]['id']
    assert roster_action(client, tournament, 'assign', user_id=third.pk, tribe_id=oak).status_code == 302
    assert roster_action(client, tournament, 'assign', user_id=third.pk, tribe_id=pine).status_code == 302
    assert roster_action(client, tournament, 'remove_player', user_id=third.pk).status_code == 302
    tournament.refresh_from_db()
    assert tournament.state['tribes'][0]['founder_id'] == second.pk
    assert tournament.state['tribes'][1]['members'] == [{'id': first.pk, 'username': first.username}]
    assert not TournamentParticipant.objects.filter(tournament=tournament, user=third).exists()
    assert LogEntry.objects.filter(user=actor, object_id=str(tournament.pk), action_flag=CHANGE).count() == 11
    page = client.get(reverse('admin:tribes_tournament_roster', args=[tournament.pk]))
    assert page.status_code == 200
    assert b'Oak' in page.content and b'Pine' in page.content


def test_enroll_and_assignment_roll_back_together_when_tribe_is_full(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    members = baker.make('users.User', is_active=True, _quantity=8)
    for user in members:
        services.add_participant(upcoming_tournament.pk, user.pk, actor=actor)
    tournament = services.create_tribe(upcoming_tournament.pk, name='Full tribe', founder_id=members[0].pk, actor=actor)
    tribe_id = tournament.state['tribes'][0]['id']
    for user in members[1:]:
        services.assign_participant(tournament.pk, user.pk, tribe_id, actor=actor)
    newcomer = baker.make('users.User', is_active=True)
    response = roster_action(client, tournament, 'enroll', username=newcomer.username, tribe_id=tribe_id)
    assert response.status_code == 200
    assert b'at most 8 members' in response.content
    assert not TournamentParticipant.objects.filter(tournament=tournament, user=newcomer).exists()
    tournament.refresh_from_db()
    assert str(newcomer.pk) not in tournament.state['players']
    assert not LogEntry.objects.filter(object_id=str(tournament.pk), action_flag=CHANGE).exists()


def test_capacity_errors_are_shown_without_overbooking(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    upcoming_tournament.max_players = 1
    upcoming_tournament.save(update_fields=['max_players'])
    first, second = baker.make('users.User', is_active=True, _quantity=2)
    services.add_participant(upcoming_tournament.pk, first.pk, actor=actor)
    response = roster_action(client, upcoming_tournament, 'enroll', username=second.username, tribe_id='')
    assert response.status_code == 200
    assert b'This tournament is full' in response.content
    assert upcoming_tournament.participants.count() == 1


def test_admin_reassignment_is_scoped_to_one_tournament(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    player = baker.make('users.User', is_active=True)
    other = services.create_tournament(
        title='Concurrent cup', starts_at=upcoming_tournament.starts_at, max_players=12, actor=actor
    )
    for tournament in (upcoming_tournament, other):
        assert roster_action(client, tournament, 'enroll', username=player.username, tribe_id='').status_code == 302
        assert roster_action(client, tournament, 'create_tribe', name='Oak', founder_id=player.pk).status_code == 302
    assert roster_action(client, upcoming_tournament, 'remove_player', user_id=player.pk).status_code == 302
    other.refresh_from_db()
    assert other.participants.filter(user=player).exists()
    assert other.state['tribes'][0]['members'][0]['id'] == player.pk


def test_due_tournament_settings_and_roster_are_read_only(tournament_admin, upcoming_tournament):
    client, _ = tournament_admin
    player = baker.make('users.User', is_active=True)
    change_url = reverse('admin:tribes_tournament_change', args=[upcoming_tournament.pk])
    roster_url = reverse('admin:tribes_tournament_roster', args=[upcoming_tournament.pk])
    with freeze_time(upcoming_tournament.starts_at):
        page = client.get(roster_url)
        assert page.status_code == 200
        assert b'This tournament has started' in page.content
        assert b'name="operation"' not in page.content
        assert (
            roster_action(client, upcoming_tournament, 'enroll', username=player.username, tribe_id='').status_code
            == 403
        )
        assert client.post(change_url, setup_payload(timezone.now() + timedelta(days=1))).status_code == 403
        assert client.get(change_url).status_code == 200
    assert not upcoming_tournament.participants.exists()


def test_roster_requires_model_permission_and_csrf(upcoming_tournament, tournament_admin):
    url = reverse('admin:tribes_tournament_roster', args=[upcoming_tournament.pk])
    viewer = baker.make('users.User', is_staff=True)
    viewer.user_permissions.add(Permission.objects.get(codename='view_tournament', content_type__app_label='tribes'))
    client = Client()
    client.force_login(viewer)
    assert client.get(url).status_code == 200
    assert b'name="operation"' not in client.get(url).content
    assert client.post(url, {'operation': 'enroll'}).status_code == 403
    stranger = baker.make('users.User', is_staff=True)
    client.force_login(stranger)
    assert client.get(url).status_code == 403
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(tournament_admin[1])
    assert csrf_client.get(url).status_code == 200
    assert csrf_client.post(url, {'operation': 'enroll'}).status_code == 403


def test_remove_tribe_requires_confirmation_and_keeps_enrollment(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    player = baker.make('users.User', is_active=True)
    services.add_participant(upcoming_tournament.pk, player.pk, actor=actor)
    tournament = services.create_tribe(upcoming_tournament.pk, name='Oak', founder_id=player.pk, actor=actor)
    tribe_id = tournament.state['tribes'][0]['id']
    assert roster_action(client, tournament, 'remove_tribe', tribe_id=tribe_id).status_code == 200
    tournament.refresh_from_db()
    assert len(tournament.state['tribes']) == 1
    assert roster_action(client, tournament, 'remove_tribe', tribe_id=tribe_id, confirm='on').status_code == 302
    tournament.refresh_from_db()
    assert tournament.state['tribes'] == []
    assert tournament.participants.filter(user=player).exists()
    page = client.get(reverse('admin:tribes_tournament_roster', args=[tournament.pk]))
    assert b'Assign these players before the start' in page.content


def test_stale_setup_form_reports_service_rejection(tournament_admin, upcoming_tournament):
    client, _ = tournament_admin
    url = reverse('admin:tribes_tournament_change', args=[upcoming_tournament.pk])
    with patch('thenewboston.tribes.services.update_tournament', side_effect=ValidationError('The roster is locked.')):
        response = client.post(url, setup_payload(upcoming_tournament.starts_at), follow=True)
    assert response.status_code == 200
    assert b'The roster is locked.' in response.content
    upcoming_tournament.refresh_from_db()
    assert upcoming_tournament.title == 'Playtest cup'


def test_participant_records_cannot_bypass_roster_services(tournament_admin, upcoming_tournament):
    client, actor = tournament_admin
    player = baker.make('users.User', is_active=True)
    services.add_participant(upcoming_tournament.pk, player.pk, actor=actor)
    participant = upcoming_tournament.participants.get()
    assert client.post(reverse('admin:tribes_tournamentparticipant_add'), {}).status_code == 403
    url = reverse('admin:tribes_tournamentparticipant_change', args=[participant.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {}).status_code == 403
