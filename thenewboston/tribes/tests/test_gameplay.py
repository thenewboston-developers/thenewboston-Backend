from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker

from thenewboston.tribes.models import Activity

from .test_integrity import action, client_for, seed_army, snapshot

pytestmark = pytest.mark.django_db


def own_tribe(game, state):
    return next(t for t in state['tribes'] if t['id'] == game['alice_tribe'])


def give_goods(game, owner, **goods):
    season = game['season']
    season.refresh_from_db()
    season.state['players'][str(game[f'{owner}_wallet'].owner_id)]['inventory'].update(goods)
    season.save(update_fields=['state'])


def activity(game, owner='alice'):
    return list(
        Activity.objects.filter(season=game['season'], tribe_id=game[f'{owner}_tribe'])
        .order_by('id')
        .values_list('text', flat=True)
    )


def test_moving_goods_is_recorded_in_terms_of_the_pack_and_the_warehouse(active_game):
    game = active_game
    alice, season = game['alice'], game['season']
    teammate = baker.make('users.User', username='teammate')
    season.refresh_from_db()
    tribe = next(t for t in season.state['tribes'] if t['id'] == game['alice_tribe'])
    tribe['members'].append({'id': teammate.pk, 'username': teammate.username})
    season.state['players'][str(teammate.pk)] = {
        'id': teammate.pk,
        'username': teammate.username,
        'inventory': {},
        'production': {},
        'experience': {},
    }
    season.save(update_fields=['state'])
    give_goods(game, 'alice', iron_ore=30)

    action(alice, season, 'transfer_items', item='iron_ore', quantity=12, source='personal', destination='tribe')
    action(alice, season, 'transfer_items', item='iron_ore', quantity=5, source='tribe', destination='personal')
    action(
        alice,
        season,
        'transfer_items',
        item='iron_ore',
        quantity=3,
        source='personal',
        destination='personal',
        recipient_user_id=teammate.pk,
    )
    state = action(
        alice,
        season,
        'transfer_items',
        item='iron_ore',
        quantity=4,
        source='tribe',
        destination='tribe',
        recipient_tribe_id=game['bob_tribe'],
    )

    assert state['viewer']['inventory']['iron_ore'] == 20
    assert own_tribe(game, state)['inventory']['iron_ore'] == 3
    assert snapshot(client_for(teammate), season)['viewer']['inventory'] == {'iron_ore': 3}
    assert activity(game)[-4:] == [
        'Stored 12 iron ore from their pack in the warehouse.',
        'Took 5 iron ore from the warehouse into their pack.',
        'Gave 3 iron ore from their pack to teammate.',
        'Sent 4 iron ore from the warehouse to Golden Legion.',
    ]
    assert activity(game, 'bob')[-1] == 'Sent 4 iron ore from Iron Wolves into the warehouse.'
    assert not any('personal' in text or 'player ' in text for text in activity(game) + activity(game, 'bob'))


def test_shortages_name_the_pack_warehouse_wallet_or_treasury(active_game):
    game = active_game
    alice, season = game['alice'], game['season']
    give_goods(game, 'alice', iron_ore=2)
    fields = {'item': 'iron_ore', 'quantity': 5}

    short = action(alice, season, 'transfer_items', source='personal', destination='tribe', expected=400, **fields)
    assert short[0]['message'] == 'Not enough iron ore in your pack.'
    short = action(alice, season, 'transfer_items', source='tribe', destination='personal', expected=400, **fields)
    assert short[0]['message'] == 'Not enough iron ore in the warehouse.'
    short = action(alice, season, 'create_listing', kind='sell', price=2, account='tribe', expected=400, **fields)
    assert short[0]['message'] == 'Not enough iron ore in the warehouse.'
    short = action(alice, season, 'treasury_withdraw', amount=5, expected=400)
    assert short[0]['message'] == 'Not enough TNB in the treasury.'
    short = action(alice, season, 'treasury_deposit', amount=game['alice_wallet'].balance + 1, expected=400)
    assert short[0]['message'] == 'Not enough TNB in your wallet.'
    stranger = action(
        alice,
        season,
        'transfer_items',
        source='personal',
        destination='personal',
        recipient_user_id=game['bob_wallet'].owner_id,
        expected=400,
        **fields,
    )
    assert stranger[0]['message'] == 'Goods can go into a pack only when it is yours or a teammate’s.'


def test_treasury_and_market_records_name_the_wallet_and_the_treasury(active_game):
    game = active_game
    alice, bob, season = game['alice'], game['bob'], game['season']
    give_goods(game, 'alice', iron_ore=10)

    action(alice, season, 'treasury_deposit', amount=40)
    action(alice, season, 'treasury_withdraw', amount=10)
    action(alice, season, 'transfer_tnb', amount=5, recipient_tribe_id=game['bob_tribe'])
    sale = action(alice, season, 'create_listing', kind='sell', item='iron_ore', quantity=4, price=3)['listings'][-1]
    action(bob, season, 'fill_listing', listing_id=sale['id'], quantity=1, account='personal')
    action(alice, season, 'cancel_listing', listing_id=sale['id'])
    order = action(alice, season, 'create_listing', kind='buy', item='coal', quantity=2, price=6, account='tribe')[
        'listings'
    ][-1]
    action(alice, season, 'cancel_listing', listing_id=order['id'])

    assert activity(game)[-8:] == [
        'Deposited 40 TNB from their wallet into the treasury.',
        'Withdrew 10 TNB from the treasury into their wallet.',
        'Sent 5 TNB from the treasury to Golden Legion.',
        f'Listed sell order #{sale["id"]}: 4 iron ore at 3 TNB each, from their pack.',
        f'Order #{sale["id"]} filled by Golden Legion: 1 iron ore for 3 TNB (paid into the owner’s wallet).',
        f'Cancelled order #{sale["id"]}: 3 iron ore at 3 TNB each; goods returned to their pack.',
        f'Listed buy order #{order["id"]}: 2 coal at 6 TNB each, paid from the treasury.',
        f'Cancelled order #{order["id"]}: 2 coal at 6 TNB each; TNB returned to the treasury.',
    ]
    assert activity(game, 'bob')[-2:] == [
        'Sent 5 TNB from Iron Wolves into the treasury.',
        f'Filled order #{sale["id"]} with Iron Wolves: 1 iron ore at 3 TNB each (3 TNB paid from their wallet).',
    ]


def test_recruitment_applications_invitations_and_permissions(tribes_game):
    game = tribes_game
    member = baker.make('users.User', username='recruit')
    client = client_for(member)
    action(client, game['season'], 'apply', tribe_id=game['alice_tribe'])
    own = snapshot(game['alice'], game['season'])
    assert own_tribe(game, own)['applications'][0]['id'] == member.pk
    action(game['bob'], game['season'], 'accept_application', user_id=member.pk, expected=400)
    state = action(game['alice'], game['season'], 'accept_application', user_id=member.pk)
    assert len(own_tribe(game, state)['members']) == 2
    action(client, game['season'], 'invite', username='bucky', expected=403)
    action(game['alice'], game['season'], 'remove_member', user_id=member.pk)
    action(game['alice'], game['season'], 'invite', username='recruit')
    state = action(client, game['season'], 'accept_invite', tribe_id=game['alice_tribe'])
    assert state['viewer']['tribe_id'] == game['alice_tribe']


def test_player_market_sale_and_buy_order_conserve_actual_tnb(active_game):
    game = active_game
    alice, bob, season = game['alice'], game['bob'], game['season']
    stock = next(listing for listing in snapshot(alice, season)['listings'] if listing['item'] == 'timber')
    action(alice, season, 'fill_listing', listing_id=stock['id'], quantity=20, account='personal')
    state = action(
        alice, season, 'create_listing', kind='sell', item='timber', quantity=10, price=3, account='personal'
    )
    sale = next(listing for listing in state['listings'] if listing['user_id'] == game['alice_wallet'].owner_id)
    state = action(bob, season, 'fill_listing', listing_id=sale['id'], quantity=4, account='personal')
    assert state['viewer']['inventory']['timber'] == 4
    assert state['viewer']['wallet_balance'] == 988
    assert snapshot(alice, season)['viewer']['wallet_balance'] == 972
    action(alice, season, 'cancel_listing', listing_id=sale['id'])
    assert snapshot(alice, season)['viewer']['inventory']['timber'] == 16
    state = action(alice, season, 'create_listing', kind='buy', item='timber', quantity=3, price=5, account='personal')
    order = next(listing for listing in state['listings'] if listing['kind'] == 'buy')
    state = action(bob, season, 'fill_listing', listing_id=order['id'], quantity=3, account='personal')
    assert state['viewer']['wallet_balance'] == 1003
    assert state['viewer']['inventory']['timber'] == 1
    assert snapshot(alice, season)['viewer']['inventory']['timber'] == 19
    season.refresh_from_db()
    assert season.system_revenue == 40
    assert season.total_deposited - season.total_withdrawn == 40


def test_land_requires_funds_ownership_and_contiguous_expansion(active_game):
    game = active_game
    state = snapshot(game['alice'], game['season'])
    home = next(p for p in state['plots'] if p['tribe_id'] == game['alice_tribe'])
    nearby = next(
        p for p in state['plots'] if p['tribe_id'] is None and p['x'] == home['x'] + 1 and p['y'] == home['y']
    )
    far = next(p for p in state['plots'] if p['tribe_id'] is None and abs(p['x'] - home['x']) > 1)
    action(game['alice'], game['season'], 'purchase_land', plot_id=nearby['id'], expected=400)
    action(game['alice'], game['season'], 'treasury_deposit', amount=200)
    action(game['alice'], game['season'], 'purchase_land', plot_id=far['id'], expected=400)
    state = action(game['alice'], game['season'], 'purchase_land', plot_id=nearby['id'])
    assert next(p for p in state['plots'] if p['id'] == nearby['id'])['tribe_id'] == game['alice_tribe']
    action(game['bob'], game['season'], 'purchase_land', plot_id=nearby['id'], expected=400)


def test_work_orders_hold_then_release_or_cancel_without_losing_materials(active_game):
    game = active_game
    alice, season = game['alice'], game['season']
    stock = next(listing for listing in snapshot(alice, season)['listings'] if listing['item'] == 'timber')
    action(alice, season, 'fill_listing', listing_id=stock['id'], quantity=20, account='personal')
    state = action(alice, season, 'create_work_order', title='Build tools', item='timber', quantity=10)
    order = state['work_orders'][0]
    state = action(alice, season, 'contribute_work_order', work_order_id=order['id'], quantity=4, source='personal')
    assert state['viewer']['inventory']['timber'] == 16
    assert own_tribe(game, state)['inventory'].get('timber', 0) == 0
    state = action(alice, season, 'cancel_work_order', work_order_id=order['id'])
    assert own_tribe(game, state)['inventory']['timber'] == 4
    action(alice, season, 'cancel_work_order', work_order_id=order['id'], expected=400)
    state = action(alice, season, 'create_work_order', title='Reserve timber', item='timber', quantity=6)
    order = state['work_orders'][-1]
    action(alice, season, 'contribute_work_order', work_order_id=order['id'], quantity=4, source='tribe')
    state = action(alice, season, 'contribute_work_order', work_order_id=order['id'], quantity=2, source='personal')
    assert own_tribe(game, state)['inventory']['timber'] == 6
    assert state['work_orders'][-1]['status'] == 'completed'


def test_building_and_military_queue_requires_facilities_and_produces_offline(active_game):
    game = active_game
    season = game['season']
    season.refresh_from_db()
    tribe = next(t for t in season.state['tribes'] if t['id'] == game['alice_tribe'])
    tribe['inventory'] = {'timber': 100, 'stone': 100, 'iron_ingot': 10, 'lumber': 40}
    home = next(p for p in season.state['plots'] if p['tribe_id'] == tribe['id'])
    season.save()
    action(game['alice'], season, 'queue', kind='craft', item='catapult', quantity=1, plot_id=home['id'], expected=400)
    now = timezone.now()
    with freeze_time(now):
        state = action(game['alice'], season, 'queue', kind='build', item='workshop', plot_id=home['id'])
        job = state['jobs'][0]
    with freeze_time(now + timedelta(hours=1, seconds=1)):
        state = snapshot(game['alice'], season)
        assert 'workshop' in next(p for p in state['plots'] if p['id'] == home['id'])['buildings']
        assert next(j for j in state['jobs'] if j['id'] == job['id'])['status'] == 'completed'
        state = action(game['alice'], season, 'queue', kind='craft', item='catapult', quantity=1, plot_id=home['id'])
    with freeze_time(now + timedelta(hours=3, seconds=2)):
        state = snapshot(game['alice'], season)
        assert state['units'][0]['quantity'] == 1
        assert state['units'][0]['controller_id'] == game['alice_wallet'].owner_id
        assert state['viewer']['production']['catapult'] == 1
        assert Activity.objects.filter(season=season, text__contains='Completed').count() == 2
        snapshot(game['alice'], season)
        assert Activity.objects.filter(season=season, text__contains='Completed').count() == 2


@pytest.mark.parametrize('field,value', [('kind', []), ('item', {}), ('account', [])])
def test_malformed_choice_inputs_return_validation_errors(active_game, field, value):
    data = {'kind': 'sell', 'item': 'timber', 'quantity': 1, 'price': 2, 'account': 'personal'}
    data[field] = value
    action(active_game['alice'], active_game['season'], 'create_listing', expected=400, **data)


def test_military_queue_preserves_secret_target_and_completes_production_goal(active_game):
    game = active_game
    season = game['season']
    season.refresh_from_db()
    tribe = next(t for t in season.state['tribes'] if t['id'] == game['alice_tribe'])
    tribe['inventory'] = {'iron_ingot': 20, 'lumber': 40}
    home = next(p for p in season.state['plots'] if p['tribe_id'] == tribe['id'])
    home['buildings'] = ['workshop']
    enemy = next(p for p in season.state['plots'] if p['x'] == home['x'] + 1 and p['y'] == home['y'] + 1)
    enemy['tribe_id'] = game['bob_tribe']
    season.save()
    now = timezone.now()
    with freeze_time(now):
        action(game['alice'], season, 'create_work_order', title='Prepare two catapults', item='catapult', quantity=2)
        state = action(
            game['alice'],
            season,
            'queue',
            kind='craft',
            item='catapult',
            quantity=2,
            plot_id=home['id'],
            target_id=game['bob_tribe'],
        )
        assert state['jobs'][0]['target_id'] == game['bob_tribe']
        rival = snapshot(game['bob'], season)
        assert 'target_id' not in rival['jobs'][0]
    with freeze_time(now + timedelta(hours=2, seconds=1)):
        state = snapshot(game['alice'], season)
        assert state['units'][0]['quantity'] == 1
        assert state['units'][0]['target_id'] == game['bob_tribe']
        assert state['work_orders'][0]['contributed'] == 1
        rival = snapshot(game['bob'], season)
        assert 'target_id' not in rival['units'][0]
    with freeze_time(now + timedelta(hours=4, seconds=1)):
        state = snapshot(game['alice'], season)
        assert state['units'][0]['quantity'] == 2
        assert state['work_orders'][0]['status'] == 'completed'
        action(
            game['alice'],
            season,
            'contribute_work_order',
            work_order_id=state['work_orders'][0]['id'],
            quantity=1,
            expected=400,
        )


def test_activity_history_is_paginated_and_private(active_game):
    game = active_game
    season = game['season']
    Activity.objects.bulk_create(
        [
            Activity(
                season=season,
                tribe_id=game['alice_tribe'],
                user=game['alice_wallet'].owner,
                text=f'Historical transfer {index}',
            )
            for index in range(205)
        ]
    )
    first = game['alice'].get('/api/tribes/activity', {'season_id': season.pk})
    assert first.status_code == 200
    assert len(first.data['results']) == 100
    second = game['alice'].get('/api/tribes/activity', {'season_id': season.pk, 'before': first.data['next_before']})
    assert len(second.data['results']) == 100
    assert set(r['id'] for r in first.data['results']).isdisjoint(r['id'] for r in second.data['results'])
    third = game['alice'].get('/api/tribes/activity', {'season_id': season.pk, 'before': second.data['next_before']})
    assert len(third.data['results']) >= 5
    assert third.data['next_before'] is None
    rival = game['bob'].get('/api/tribes/activity', {'season_id': season.pk})
    assert not any('Historical transfer' in r['text'] for r in rival.data['results'])
    assert client_for(baker.make('users.User')).get('/api/tribes/activity', {'season_id': season.pk}).status_code == 403
    assert client_for().get('/api/tribes/activity', {'season_id': season.pk}).status_code in (401, 403)
    assert game['alice'].get('/api/tribes/activity', {'season_id': season.pk, 'before': 'bad'}).status_code == 400


def test_controller_permission_rejection_is_distinct_from_authentication_failure(active_game):
    game = active_game
    unit_id, plot_id = seed_army(game)
    response = action(game['bob'], game['season'], 'deploy', unit_id=unit_id, plot_id=plot_id, expected=403)
    assert response['code'] == 'tribes_action_forbidden'
    assert 'controller' in response['detail']
    unauthenticated = client_for().post('/api/tribes/actions', {'action': 'deploy'}, format='json')
    assert unauthenticated.status_code in (401, 403)
    assert unauthenticated.data.get('code') != 'tribes_action_forbidden'


def test_correspondence_history_paginates_without_exposing_unrelated_tribes(active_game):
    game = active_game
    season = game['season']
    season.refresh_from_db()
    # Messages alternate private tribe chat and letters visible to both tribes.
    for index in range(205):
        message_id = season.state['next_id']
        season.state['next_id'] += 1
        season.state['messages'].append(
            {
                'id': message_id,
                'from_tribe_id': game['alice_tribe'],
                'to_tribe_id': game['alice_tribe'] if index % 2 == 0 else game['bob_tribe'],
                'user_id': game['alice_wallet'].owner_id,
                'username': 'bucky',
                'text': f'Letter {index}',
                'created_at': timezone.now().isoformat(),
            }
        )
    season.status = 'finished'
    season.save(update_fields=['state', 'status'])
    first = game['alice'].get('/api/tribes/messages', {'season_id': season.pk})
    assert first.status_code == 200
    assert len(first.data['results']) == 100
    assert first.data['results'][0]['text'] == 'Letter 204'
    second = game['alice'].get('/api/tribes/messages', {'season_id': season.pk, 'before': first.data['next_before']})
    assert len(second.data['results']) == 100
    assert set(r['id'] for r in first.data['results']).isdisjoint(r['id'] for r in second.data['results'])
    third = game['alice'].get('/api/tribes/messages', {'season_id': season.pk, 'before': second.data['next_before']})
    assert len(third.data['results']) == 5
    assert third.data['next_before'] is None
    rival = game['bob'].get('/api/tribes/messages', {'season_id': season.pk})
    assert len(rival.data['results']) == 100
    assert all(message['to_tribe_id'] == game['bob_tribe'] for message in rival.data['results'])
    outsider = client_for(baker.make('users.User')).get('/api/tribes/messages', {'season_id': season.pk})
    assert outsider.status_code == 403
    assert client_for().get('/api/tribes/messages', {'season_id': season.pk}).status_code in (401, 403)
    assert game['alice'].get('/api/tribes/messages', {'season_id': season.pk, 'before': 'bad'}).status_code == 400
