"""Independent checks for money conservation, privacy, and the weekly cutoff."""

from datetime import timedelta
from random import Random
from uuid import uuid4

import pytest
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.tribes.models import ActionReceipt, Tournament
from thenewboston.tribes.rules import resolve_battle
from thenewboston.tribes.services import add_participant, create_tournament, create_tribe
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def action(client, tournament, action_name, *, expected=200, request_id=None, **fields):
    response = client.post(
        '/api/tribes/actions',
        {'tournament_id': tournament.pk, 'request_id': str(request_id or uuid4()), 'action': action_name, **fields},
        format='json',
    )
    assert response.status_code == expected, response.data
    return response.data


def snapshot(client, tournament):
    response = client.get('/api/tribes/state', {'tournament_id': tournament.pk})
    assert response.status_code == 200, response.data
    return response.data


def seed_army(game, *, owner='alice', quantity=10):
    tournament = game['tournament']
    tournament.refresh_from_db()
    plot = next(p for p in tournament.state['plots'] if p['tribe_id'] == game[f'{owner}_tribe'])
    unit_id = tournament.state['next_id']
    tournament.state['next_id'] += 1
    tournament.state['units'].append(
        {
            'id': unit_id,
            'tribe_id': game[f'{owner}_tribe'],
            'controller_id': game[f'{owner}_wallet'].owner_id,
            'item': 'catapult',
            'quantity': quantity,
            'plot_id': plot['id'],
            'target_id': game['bob_tribe'] if owner == 'alice' else game['alice_tribe'],
        }
    )
    tournament.save(update_fields=['state'])
    return unit_id, plot['id']


@pytest.fixture
def tribes_game(bucky_tnb_wallet, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    alice = client_for(bucky_tnb_wallet.owner)
    bob = client_for(dmitry_tnb_wallet.owner)
    admin = baker.make('users.User', is_staff=True, is_superuser=True)
    tournament = create_tournament(
        title='Test tournament', starts_at=timezone.now() + timedelta(days=1), max_players=12, actor=admin
    )
    add_participant(tournament.pk, bucky_tnb_wallet.owner_id, actor=admin)
    add_participant(tournament.pk, dmitry_tnb_wallet.owner_id, actor=admin)
    create_tribe(tournament.pk, name='Iron Wolves', founder_id=bucky_tnb_wallet.owner_id, actor=admin)
    create_tribe(tournament.pk, name='Golden Legion', founder_id=dmitry_tnb_wallet.owner_id, actor=admin)
    first = snapshot(alice, tournament)
    second = snapshot(bob, tournament)
    return {
        'admin': admin,
        'alice': alice,
        'alice_wallet': bucky_tnb_wallet,
        'alice_tribe': first['viewer']['tribe_id'],
        'bob': bob,
        'bob_wallet': dmitry_tnb_wallet,
        'bob_tribe': second['viewer']['tribe_id'],
        'tournament': tournament,
    }


@pytest.fixture
def active_game(tribes_game):
    tournament = tribes_game['tournament']
    tournament.starts_at = timezone.now() - timedelta(seconds=1)
    tournament.ends_at = tournament.starts_at + timedelta(days=7)
    tournament.save(update_fields=['starts_at', 'ends_at'])
    snapshot(tribes_game['alice'], tournament)
    tournament.refresh_from_db()
    assert tournament.status == 'active'
    return tribes_game


def test_actual_wallet_funding_is_idempotent_and_never_granted(active_game):
    game = active_game
    wallet = game['alice_wallet']
    assert snapshot(game['alice'], game['tournament'])['viewer']['wallet_balance'] == 1000
    request_id = uuid4()
    first = action(game['alice'], game['tournament'], 'treasury_deposit', amount=600, request_id=request_id)
    retry = action(game['alice'], game['tournament'], 'treasury_deposit', amount=600, request_id=request_id)
    assert first['viewer']['wallet_balance'] == retry['viewer']['wallet_balance'] == 400
    action(game['alice'], game['tournament'], 'treasury_deposit', amount=601, request_id=request_id, expected=409)
    wallet.refresh_from_db()
    assert wallet.balance == 400
    tribe = next(t for t in retry['tribes'] if t['id'] == game['alice_tribe'])
    assert tribe['treasury'] == 600
    assert ActionReceipt.objects.filter(actor=wallet.owner, request_id=request_id).count() == 1


def test_recruitment_cannot_take_treasury_funds_before_roster_locks(tribes_game):
    game = tribes_game
    action(game['alice'], game['tournament'], 'treasury_deposit', amount=100, expected=400)
    game['alice_wallet'].refresh_from_db()
    assert game['alice_wallet'].balance == 1000


@pytest.mark.parametrize('amount', [True, False, 0, -1, 1.5, '1', 10**20])
def test_treasury_rejects_invalid_amounts_without_mutation(active_game, amount):
    game = active_game
    action(game['alice'], game['tournament'], 'treasury_deposit', amount=amount, expected=400)
    game['alice_wallet'].refresh_from_db()
    assert game['alice_wallet'].balance == 1000


def test_roster_and_founder_permissions_lock_at_start(active_game):
    game = active_game
    action(game['alice'], game['tournament'], 'leave', expected=400)
    action(game['alice'], game['tournament'], 'invite', username='dmitry', expected=400)
    action(game['bob'], game['tournament'], 'apply', tribe_id=game['alice_tribe'], expected=400)
    action(game['alice'], game['tournament'], 'update_tribe', name='Changed', expected=400)
    assert snapshot(game['alice'], game['tournament'])['viewer']['tribe_id'] == game['alice_tribe']


@pytest.mark.parametrize('item', [[], {}, None, True, 123])
def test_malformed_building_item_is_a_validation_error(active_game, item):
    game = active_game
    own_plot = next(
        p for p in snapshot(game['alice'], game['tournament'])['plots'] if p['tribe_id'] == game['alice_tribe']
    )
    action(game['alice'], game['tournament'], 'queue', kind='build', item=item, plot_id=own_plot['id'], expected=400)


def test_public_and_rival_views_never_expose_treasury_or_correspondence(active_game):
    game = active_game
    alice, bob, tournament = game['alice'], game['bob'], game['tournament']
    action(alice, tournament, 'treasury_deposit', amount=123)
    action(alice, tournament, 'message', to_tribe_id=game['alice_tribe'], text='Private military plan')
    action(bob, tournament, 'message', to_tribe_id=game['alice_tribe'], text='A diplomatic proposal')
    own = snapshot(alice, tournament)
    rival = snapshot(bob, tournament)
    stranger = snapshot(client_for(baker.make('users.User')), tournament)
    public = snapshot(client_for(), tournament)
    assert {'Private military plan', 'A diplomatic proposal'} <= {m['text'] for m in own['messages']}
    assert {m['text'] for m in rival['messages']} == {'A diplomatic proposal'}
    for state in (stranger, public):
        assert state['messages'] == []
        assert state['activity'] == []
        assert state['work_orders'] == []
    for state in (rival, stranger, public):
        tribe = next(t for t in state['tribes'] if t['id'] == game['alice_tribe'])
        assert tribe['treasury'] is None
        assert tribe['inventory'] is None


def test_unit_targets_are_secret_and_transfers_clear_control_and_target(active_game):
    game = active_game
    tournament = game['tournament']
    tournament.refresh_from_db()
    own_plot = next(p for p in tournament.state['plots'] if p['tribe_id'] == game['alice_tribe'])
    other_plot = next(p for p in tournament.state['plots'] if p['tribe_id'] == game['bob_tribe'])
    other_plot.update(x=own_plot['x'] + 1, y=own_plot['y'] + 1)
    unit_id = tournament.state['next_id']
    tournament.state['next_id'] += 1
    tournament.state['units'].append(
        {
            'id': unit_id,
            'tribe_id': game['alice_tribe'],
            'controller_id': game['alice_wallet'].owner_id,
            'item': 'catapult',
            'quantity': 3,
            'plot_id': own_plot['id'],
            'target_id': game['bob_tribe'],
        }
    )
    tournament.save(update_fields=['state'])
    own = snapshot(game['alice'], tournament)['units'][0]
    assert own['target_id'] == game['bob_tribe']
    for viewer in (game['bob'], client_for()):
        assert 'target_id' not in snapshot(viewer, tournament)['units'][0]
    action(
        game['bob'],
        tournament,
        'deploy',
        unit_id=unit_id,
        plot_id=other_plot['id'],
        target_id=game['alice_tribe'],
        expected=403,
    )
    action(
        game['alice'],
        tournament,
        'transfer_unit',
        unit_id=unit_id,
        recipient_user_id=game['bob_wallet'].owner_id,
        plot_id=other_plot['id'],
    )
    received = snapshot(game['bob'], tournament)['units'][0]
    assert received['target_id'] is None
    assert received['controller_id'] == game['bob_wallet'].owner_id
    assert received['tribe_id'] == game['bob_tribe']
    assert received['quantity'] == 3
    action(game['alice'], tournament, 'deploy', unit_id=unit_id, plot_id=own_plot['id'], expected=403)


def test_gathering_progress_is_retained_when_cancelled_and_does_not_repeat(active_game):
    game = active_game
    tournament = game['tournament']
    own_plot = next(p for p in snapshot(game['alice'], tournament)['plots'] if p['tribe_id'] == game['alice_tribe'])
    now = timezone.now()
    with freeze_time(now):
        state = action(
            game['alice'], tournament, 'queue', kind='gather', plot_id=own_plot['id'], hours=4, destination='personal'
        )
        job_id = state['jobs'][0]['id']
    with freeze_time(now + timedelta(hours=1, minutes=15)):
        state = action(game['alice'], tournament, 'cancel_job', job_id=job_id)
        assert state['viewer']['inventory']['wheat'] == 12
        assert state['jobs'][0]['completed'] == 12
        assert state['jobs'][0]['status'] == 'cancelled'
    with freeze_time(now + timedelta(hours=5)):
        state = snapshot(game['alice'], tournament)
        assert state['viewer']['inventory']['wheat'] == 12
        assert state['viewer']['production']['wheat'] == 12


def test_crafting_cancellation_returns_only_unfinished_materials(active_game):
    game = active_game
    tournament = game['tournament']
    tournament.refresh_from_db()
    tournament.state['players'][str(game['alice_wallet'].owner_id)]['inventory']['timber'] = 20
    tournament.save(update_fields=['state'])
    own_plot = next(p for p in tournament.state['plots'] if p['tribe_id'] == game['alice_tribe'])
    now = timezone.now()
    with freeze_time(now):
        state = action(
            game['alice'],
            tournament,
            'queue',
            kind='craft',
            item='lumber',
            quantity=10,
            plot_id=own_plot['id'],
            source='personal',
            destination='personal',
        )
        job_id = state['jobs'][0]['id']
        assert state['viewer']['inventory']['timber'] == 0
    with freeze_time(now + timedelta(minutes=5)):
        state = action(game['alice'], tournament, 'cancel_job', job_id=job_id)
        assert state['viewer']['inventory']['lumber'] == 2
        assert state['viewer']['inventory']['timber'] == 16
        action(game['alice'], tournament, 'cancel_job', job_id=job_id, expected=400)
    with freeze_time(now + timedelta(hours=1)):
        assert snapshot(game['alice'], tournament)['viewer']['inventory'] == {'timber': 16, 'lumber': 2}


def test_cutoff_refunds_treasury_and_buy_escrow_once_and_replays_receipt(active_game):
    game = active_game
    alice, tournament, wallet = game['alice'], game['tournament'], game['alice_wallet']
    request_id = uuid4()
    action(alice, tournament, 'treasury_deposit', amount=333, request_id=request_id)
    action(alice, tournament, 'create_listing', kind='buy', item='coal', quantity=10, price=7, account='personal')
    action(alice, tournament, 'create_listing', kind='buy', item='wheat', quantity=10, price=3, account='tribe')
    wallet.refresh_from_db()
    assert wallet.balance == 597
    with freeze_time(tournament.ends_at + timedelta(days=2)):
        for _ in range(2):
            state = snapshot(alice, tournament)
            assert state['tournament']['status'] == 'finished'
            assert state['viewer']['wallet_balance'] == 1000
        action(alice, tournament, 'treasury_deposit', amount=333, request_id=request_id)
        action(alice, tournament, 'treasury_deposit', amount=1, expected=400)
        assert alice.get('/api/tribes/state').status_code == 400
        assert Tournament.objects.count() == 1
    tournament.refresh_from_db()
    assert tournament.total_deposited == tournament.total_withdrawn
    assert all(t['treasury'] == 0 for t in tournament.state['tribes'])


def test_late_worker_wakeup_cannot_produce_beyond_final_cutoff(active_game):
    game = active_game
    tournament = game['tournament']
    own_plot = next(p for p in snapshot(game['alice'], tournament)['plots'] if p['tribe_id'] == game['alice_tribe'])
    now = timezone.now()
    with freeze_time(now):
        action(
            game['alice'], tournament, 'queue', kind='gather', plot_id=own_plot['id'], hours=4, destination='personal'
        )
    # A shortened administrative deadline, or an old queued assignment crossing
    # a changed schedule, must still obey the server's absolute cutoff.
    tournament.ends_at = now + timedelta(hours=1)
    tournament.save(update_fields=['ends_at'])
    with freeze_time(now + timedelta(days=2)):
        first = snapshot(game['alice'], tournament)
        second = snapshot(game['alice'], tournament)
    assert first['tournament']['status'] == 'finished'
    assert first['viewer']['inventory']['wheat'] == second['viewer']['inventory']['wheat'] == 10


def test_military_market_conserves_units_tnb_and_target_privacy(active_game):
    game = active_game
    tournament = game['tournament']
    unit_id, _ = seed_army(game)
    created = action(
        game['alice'],
        tournament,
        'create_listing',
        kind='sell',
        item='catapult',
        unit_id=unit_id,
        quantity=6,
        price=20,
        account='personal',
    )
    listing = next(row for row in created['listings'] if row['item'] == 'catapult')
    public_listing = next(row for row in snapshot(client_for(), tournament)['listings'] if row['id'] == listing['id'])
    assert 'target_id' not in public_listing
    assert 'target_id' not in public_listing.get('escrow_unit', {})
    buyer_plot = next(p for p in created['plots'] if p['tribe_id'] == game['bob_tribe'])
    request_id = uuid4()
    for _ in range(2):
        bought = action(
            game['bob'],
            tournament,
            'fill_listing',
            listing_id=listing['id'],
            quantity=3,
            account='personal',
            plot_id=buyer_plot['id'],
            request_id=request_id,
        )
    purchased = [u for u in bought['units'] if u['tribe_id'] == game['bob_tribe']]
    assert sum(u['quantity'] for u in purchased) == 3
    assert all(u['controller_id'] == game['bob_wallet'].owner_id and u['target_id'] is None for u in purchased)
    cancelled = action(game['alice'], tournament, 'cancel_listing', listing_id=listing['id'])
    assert sum(u['quantity'] for u in cancelled['units']) == 10
    assert sum(u['quantity'] for u in cancelled['units'] if u['tribe_id'] == game['alice_tribe']) == 7
    for wallet in (game['alice_wallet'], game['bob_wallet']):
        wallet.refresh_from_db()
    assert (game['alice_wallet'].balance, game['bob_wallet'].balance) == (1060, 940)


def test_military_sale_capacity_failure_does_not_charge_or_consume_listing(active_game):
    game = active_game
    tournament = game['tournament']
    unit_id, _ = seed_army(game)
    _, buyer_plot_id = seed_army(game, owner='bob', quantity=100)
    created = action(
        game['alice'],
        tournament,
        'create_listing',
        kind='sell',
        item='catapult',
        unit_id=unit_id,
        quantity=10,
        price=20,
        account='personal',
    )
    listing = next(row for row in created['listings'] if row['item'] == 'catapult')
    action(
        game['bob'],
        tournament,
        'fill_listing',
        listing_id=listing['id'],
        quantity=1,
        account='personal',
        plot_id=buyer_plot_id,
        expected=400,
    )
    final = snapshot(game['bob'], tournament)
    assert next(row for row in final['listings'] if row['id'] == listing['id'])['quantity'] == 10
    for wallet in (game['alice_wallet'], game['bob_wallet']):
        wallet.refresh_from_db()
        assert wallet.balance == 1000


def test_military_sale_reserves_origin_capacity_until_cancellation(active_game):
    game = active_game
    tournament = game['tournament']
    seller_unit, seller_plot = seed_army(game, quantity=100)
    buyer_unit, _ = seed_army(game, owner='bob', quantity=1)
    created = action(
        game['alice'],
        tournament,
        'create_listing',
        kind='sell',
        item='catapult',
        unit_id=seller_unit,
        quantity=60,
        price=20,
        account='personal',
    )
    listing = next(row for row in created['listings'] if row['item'] == 'catapult')
    action(
        game['bob'],
        tournament,
        'transfer_unit',
        unit_id=buyer_unit,
        plot_id=seller_plot,
        recipient_user_id=game['alice_wallet'].owner_id,
        expected=400,
    )
    restored = action(game['alice'], tournament, 'cancel_listing', listing_id=listing['id'])
    assert sum(u['quantity'] for u in restored['units'] if u['tribe_id'] == game['alice_tribe']) == 100


def test_battle_is_simultaneous_and_proportional_with_conserved_damage():
    tribes = [{'id': i, 'name': f'Tribe {i}'} for i in range(1, 4)]
    plots = [{'id': i, 'tribe_id': i, 'x': i, 'y': i} for i in range(1, 4)]
    units = [
        {'id': 1, 'tribe_id': 1, 'controller_id': 11, 'item': 'catapult', 'quantity': 1, 'plot_id': 1, 'target_id': 3},
        {'id': 2, 'tribe_id': 2, 'controller_id': 22, 'item': 'infantry', 'quantity': 1, 'plot_id': 2, 'target_id': 3},
        {
            'id': 3,
            'tribe_id': 3,
            'controller_id': 33,
            'item': 'barricade',
            'quantity': 1,
            'plot_id': 3,
            'target_id': None,
        },
        {'id': 4, 'tribe_id': 3, 'controller_id': 33, 'item': 'trebuchet', 'quantity': 1, 'plot_id': 3, 'target_id': 1},
    ]
    result = resolve_battle(tribes, units, plots)
    rows = {row['tribe_id']: row for row in result['standings']}
    assert rows[3]['raw_incoming'] == 90
    assert rows[3]['blocked'] == 30
    assert rows[3]['incoming'] == 60
    assert rows[1]['outgoing'] == 53
    assert rows[2]['outgoing'] == 7
    assert rows[3]['outgoing'] == rows[1]['incoming'] == 200
    assert sum(row['score'] for row in rows.values()) == 0
    assert sum(row['incoming'] for row in rows.values()) == sum(row['outgoing'] for row in rows.values())


def test_battle_ignores_missing_self_and_out_of_range_targets_and_shares_ties():
    tribes = [{'id': i, 'name': f'Tribe {i}'} for i in range(1, 4)]
    plots = [{'id': i, 'tribe_id': i, 'x': i * 10, 'y': i * 10} for i in range(1, 4)]
    units = [
        {
            'id': i,
            'tribe_id': 1,
            'controller_id': 11,
            'item': 'infantry',
            'quantity': 10,
            'plot_id': 1,
            'target_id': target,
        }
        for i, target in enumerate((None, 1, 2, 999), 1)
    ]
    result = resolve_battle(tribes, units, plots)
    assert result['attacks'] == []
    assert all(row['score'] == 0 and row['rank'] == 1 for row in result['standings'])


def test_battle_conserves_damage_across_varied_multi_tribe_worlds():
    random = Random(1409)
    tribes = [{'id': i, 'name': f'Tribe {i}'} for i in range(1, 9)]
    plots = [{'id': i, 'tribe_id': i, 'x': i % 4, 'y': i // 4} for i in range(1, 9)]
    for _ in range(25):
        units = []
        for unit_id in range(1, 65):
            tribe_id = random.randint(1, 8)
            units.append(
                {
                    'id': unit_id,
                    'tribe_id': tribe_id,
                    'controller_id': tribe_id,
                    'item': random.choice(['infantry', 'catapult', 'trebuchet', 'barricade', 'stone_wall']),
                    'quantity': random.randint(1, 10),
                    'plot_id': tribe_id,
                    'target_id': random.randint(1, 8),
                }
            )
        result = resolve_battle(tribes, units, plots)
        rows = result['standings']
        assert sum(row['score'] for row in rows) == 0
        assert sum(row['outgoing'] for row in rows) == sum(row['incoming'] for row in rows)
        for row in rows:
            assert row['incoming'] >= 0
            assert row['incoming'] + row['blocked'] == row['raw_incoming']
            assert row['blocked'] <= row['defense']
        for attack in result['attacks']:
            assert 0 <= attack['effective_damage'] <= attack['raw_damage']
        reverse = resolve_battle(list(reversed(tribes)), list(reversed(units)), list(reversed(plots)))
        assert [(row['tribe_id'], row['score']) for row in reverse['standings']] == [
            (row['tribe_id'], row['score']) for row in rows
        ]
