from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from thenewboston.tribes.management.commands.verify_tribes import verify_season
from thenewboston.tribes.models import MoneyEntry, Season

pytestmark = pytest.mark.django_db


@pytest.fixture
def accounted_season(bucky_tnb_wallet):
    season = Season.objects.create(
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=7),
        status='active',
        currency=bucky_tnb_wallet.currency,
        total_deposited=500,
        total_withdrawn=100,
        system_revenue=50,
        state={
            'tribes': [{'id': 1, 'treasury': 200}],
            'listings': [{'id': 1, 'kind': 'buy', 'quantity': 30, 'price': 5}],
        },
    )
    MoneyEntry.objects.create(season=season, wallet=bucky_tnb_wallet, amount=500, reason='deposit')
    MoneyEntry.objects.create(season=season, wallet=bucky_tnb_wallet, amount=-100, reason='withdraw')
    return season


def test_verification_does_not_move_coins_or_change_the_world(accounted_season, bucky_tnb_wallet):
    original = accounted_season.state.copy()
    initial_balance = bucky_tnb_wallet.balance
    output = StringIO()
    call_command('verify_tribes', stdout=output)
    assert 'Tribes verified' in output.getvalue()
    accounted_season.refresh_from_db()
    bucky_tnb_wallet.refresh_from_db()
    assert accounted_season.state == original
    assert bucky_tnb_wallet.balance == initial_balance
    assert MoneyEntry.objects.count() == 2


def test_verification_detects_missing_wallet_movement(accounted_season):
    accounted_season.money_entries.filter(amount__lt=0).delete()
    with pytest.raises(CommandError, match='wallet ledger'):
        verify_season(accounted_season)


def test_verification_detects_reserve_imbalance(accounted_season):
    accounted_season.state['tribes'][0]['treasury'] += 1
    with pytest.raises(CommandError, match='not conserved'):
        verify_season(accounted_season)


def test_verification_rejects_unsettled_finished_season(accounted_season):
    accounted_season.status = 'finished'
    with pytest.raises(CommandError, match='unsettled TNB'):
        verify_season(accounted_season)


def test_verification_detects_a_corrupt_battle(accounted_season):
    accounted_season.state['battle'] = {'standings': [{'outgoing': 100, 'incoming': 0, 'score': 100}]}
    with pytest.raises(CommandError, match='battle damage'):
        verify_season(accounted_season)
