from dataclasses import FrozenInstanceError, replace
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError

from thenewboston.casino.contracts import GameDefinition
from thenewboston.casino.models import CasinoGameConfig
from thenewboston.casino.registry import GameRegistry, get_rules, registry
from thenewboston.casino.services import casino_summary
from thenewboston.casino.views import BetSerializer
from thenewboston.roulette.catalog import ROULETTE
from thenewboston.roulette.rules import ROULETTE_V1
from thenewboston.slots.catalog import SLOTS
from thenewboston.slots.rules import SLOTS_V1, SLOTS_V2


def test_installed_game_apps_register_catalogs_in_unchanged_order():
    assert apps.get_app_config('slots').name == 'thenewboston.slots'
    assert apps.get_app_config('roulette').name == 'thenewboston.roulette'
    assert registry.games == (SLOTS, ROULETTE)
    assert get_rules('slots', 1) is SLOTS_V1
    assert get_rules('slots', 2) is SLOTS_V2
    assert SLOTS.default_version == 2
    assert get_rules('roulette', 1) is ROULETTE_V1
    assert list(BetSerializer().fields['game'].choices) == ['slots', 'roulette']


def test_registration_order_does_not_change_public_catalog_order_and_ready_can_repeat():
    local = GameRegistry()
    local.register(ROULETTE)
    local.register(SLOTS)
    local.register(SLOTS)
    assert local.games == (SLOTS, ROULETTE)
    assert len(local.rules) == 3


def test_versions_are_not_overwritten_and_registry_is_read_only():
    local = GameRegistry()
    local.register(SLOTS)
    with pytest.raises(ValueError, match='already registered'):
        local.register(replace(SLOTS, catalog_order=10))
    with pytest.raises(TypeError):
        local.rules[('slots', 1)] = ROULETTE_V1
    with pytest.raises(FrozenInstanceError):
        SLOTS_V1.version = 2
    assert local.get_rules('slots', 1) is SLOTS_V1


@pytest.mark.parametrize(
    'definition',
    [
        replace(SLOTS, rules=()),
        replace(SLOTS, rules=(SLOTS_V1, SLOTS_V1)),
        replace(SLOTS, rules=(ROULETTE_V1,)),
        replace(SLOTS, default_version=3),
        replace(SLOTS, default_min_bet=0),
        replace(SLOTS, rules=(replace(SLOTS_V1, catalog_multiplier=1),)),
        replace(SLOTS, rules=(replace(SLOTS_V1, max_multiplier=100.5),)),
        replace(SLOTS, rules=(replace(SLOTS_V1, house_edge=1),)),
    ],
)
def test_invalid_definition_cannot_partially_register(definition):
    local = GameRegistry()
    with pytest.raises(ValueError):
        local.register(definition)
    assert local.games == ()
    assert not local.rules


@pytest.mark.parametrize('game,version', [('unknown', 1), ('slots', 99), ([], 1), ('roulette', {})])
def test_unknown_rules_keep_the_existing_validation_message(game, version):
    with pytest.raises(ValueError, match='Unsupported game or rules version.'):
        get_rules(game, version)


@pytest.mark.django_db
def test_future_game_catalog_and_serializer_need_no_shared_game_branch(monkeypatch):
    local = GameRegistry()
    example = replace(SLOTS_V1, game='example', version=7, name='Example')
    local.register(GameDefinition(game='example', rules=(example,), default_version=7))
    monkeypatch.setattr('thenewboston.casino.services.registry', local)
    monkeypatch.setattr('thenewboston.casino.views.registry', local)
    CasinoGameConfig.objects.create(game='example', rules_version=7)
    game = casino_summary()['games'][0]
    assert game['id'] == 'example'
    assert game['name'] == 'Example'
    assert game['rules_version'] == 7
    assert 'payout_table' in game
    assert list(BetSerializer().fields['game'].choices) == ['example']


@pytest.mark.django_db
def test_missing_configuration_and_uninstalled_version_remain_closed():
    CasinoGameConfig.objects.filter(game='slots').delete()
    CasinoGameConfig.objects.update_or_create(game='roulette', defaults={'rules_version': 99})
    slots, roulette = casino_summary()['games']
    assert slots['rules_version'] == 2
    assert not slots['enabled'] and not slots['available']
    assert roulette['rules_version'] == 99
    assert roulette['max_multiplier'] == 36
    assert not roulette['enabled'] and not roulette['available']


@pytest.mark.django_db
def test_verification_dispatches_to_every_registered_ruleset(monkeypatch):
    called = []
    monkeypatch.setattr(type(SLOTS_V1), 'verify', lambda self: called.append((self.game, self.version)))
    monkeypatch.setattr(type(ROULETTE_V1), 'verify', lambda self: called.append((self.game, self.version)))
    call_command('verify_casino', stdout=StringIO())
    assert called == [('roulette', 1), ('slots', 1), ('slots', 2)]


@pytest.mark.django_db
def test_verification_reports_a_game_owned_failure(monkeypatch):
    def fail(self):
        raise ValueError('Game rules failed validation')

    monkeypatch.setattr(type(ROULETTE_V1), 'verify', fail)
    with pytest.raises(CommandError, match='Game rules failed validation'):
        call_command('verify_casino', stdout=StringIO())
