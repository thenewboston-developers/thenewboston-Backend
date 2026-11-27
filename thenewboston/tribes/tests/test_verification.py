from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from thenewboston.tribes.management.commands.verify_tribes import verify_tournament
from thenewboston.tribes.models import MoneyEntry, Tournament, TournamentParticipant

pytestmark = pytest.mark.django_db


@pytest.fixture
def accounted_tournament(bucky_tnb_wallet):
    tournament = Tournament.objects.create(
        title='Accounting',
        max_players=12,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=7),
        status='active',
        currency=bucky_tnb_wallet.currency,
        total_deposited=500,
        total_withdrawn=100,
        system_revenue=50,
        state={
            'tribes': [
                {
                    'id': 1,
                    'treasury': 200,
                    'founder_id': bucky_tnb_wallet.owner_id,
                    'members': [{'id': bucky_tnb_wallet.owner_id}],
                }
            ],
            'listings': [{'id': 1, 'kind': 'buy', 'quantity': 30, 'price': 5}],
        },
    )
    TournamentParticipant.objects.create(tournament=tournament, user=bucky_tnb_wallet.owner)
    MoneyEntry.objects.create(tournament=tournament, wallet=bucky_tnb_wallet, amount=500, reason='deposit')
    MoneyEntry.objects.create(tournament=tournament, wallet=bucky_tnb_wallet, amount=-100, reason='withdraw')
    return tournament


def test_verification_does_not_move_coins_or_change_the_world(accounted_tournament, bucky_tnb_wallet):
    original = accounted_tournament.state.copy()
    initial_balance = bucky_tnb_wallet.balance
    output = StringIO()
    call_command('verify_tribes', stdout=output)
    assert 'Tribes verified' in output.getvalue()
    accounted_tournament.refresh_from_db()
    bucky_tnb_wallet.refresh_from_db()
    assert accounted_tournament.state == original
    assert bucky_tnb_wallet.balance == initial_balance
    assert MoneyEntry.objects.count() == 2


def test_verification_detects_missing_wallet_movement(accounted_tournament):
    accounted_tournament.money_entries.filter(amount__lt=0).delete()
    with pytest.raises(CommandError, match='wallet ledger'):
        verify_tournament(accounted_tournament)


def test_verification_detects_reserve_imbalance(accounted_tournament):
    accounted_tournament.state['tribes'][0]['treasury'] += 1
    with pytest.raises(CommandError, match='not conserved'):
        verify_tournament(accounted_tournament)


def test_verification_rejects_unsettled_finished_tournament(accounted_tournament):
    accounted_tournament.status = 'finished'
    with pytest.raises(CommandError, match='unsettled TNB'):
        verify_tournament(accounted_tournament)


def test_verification_detects_a_corrupt_battle(accounted_tournament):
    accounted_tournament.state['battle'] = {'standings': [{'outgoing': 100, 'incoming': 0, 'score': 100}]}
    with pytest.raises(CommandError, match='battle damage'):
        verify_tournament(accounted_tournament)


@pytest.mark.parametrize('corruption', ['duplicate', 'unenrolled', 'captain', 'capacity'])
def test_verification_detects_invalid_roster(accounted_tournament, corruption):
    tournament = accounted_tournament
    tribe = tournament.state['tribes'][0]
    if corruption == 'duplicate':
        tribe['members'].append(tribe['members'][0].copy())
    elif corruption == 'unenrolled':
        tribe['members'].append({'id': tribe['founder_id'] + 1000})
    elif corruption == 'captain':
        tribe['founder_id'] += 1000
    else:
        tournament.max_players = 0
    with pytest.raises(CommandError):
        verify_tournament(tournament)
