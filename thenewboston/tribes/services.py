"""Authoritative Tribes state machine.

World -> Season -> Wallet (sorted owner IDs) is the lock order. The single world
lock deliberately serializes the MVP's economy, production, and final battle.
Every real TNB movement has a permanent ledger entry and conservation is checked
before committing. Clients never supply balances, rates, output, or combat scores.
"""

import copy
import hashlib
import json
import logging
import math
import random
import re
from datetime import timedelta
from uuid import UUID

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from thenewboston.currencies.models import Currency
from thenewboston.general.utils.image import process_image, validate_image_dimensions
from thenewboston.users.models import User
from thenewboston.wallets.models import Wallet

from .models import ActionReceipt, Activity, MoneyEntry, Season, World
from .rules import (
    BUILDING_CAPACITY,
    BUILDINGS,
    DEFENSES,
    GATHER_CAPACITY,
    LAND,
    MAX_MEMBERS,
    OPENING_STOCK,
    QUEUE_SECONDS,
    RECIPES,
    TRADE_ITEMS,
    UNIT_CAPACITY,
    UNITS,
    catalog,
    distance,
    resolve_battle,
)

logger = logging.getLogger(__name__)
EMBLEM_IMAGE_SIZE = 512
MAX_AMOUNT = 1_000_000_000
MAX_TOTAL = 9_007_199_254_740_991
# The names players see for the two accounts. Goods are kept in a player's own pack or the tribe's shared
# warehouse; TNB is kept in a player's own wallet or the tribe's shared treasury.
PLACES = {'goods': {'personal': 'pack', 'tribe': 'warehouse'}, 'tnb': {'personal': 'wallet', 'tribe': 'treasury'}}


class RequestConflict(APIException):
    status_code = 409
    default_detail = 'This request ID was already used for a different action.'


def new_state():
    return {
        'next_id': 1,
        'tribes': [],
        'players': {},
        'plots': [],
        'jobs': [],
        'units': [],
        'listings': [],
        'messages': [],
        'work_orders': [],
        'battle': None,
    }


def _id(state):
    value = state['next_id']
    state['next_id'] += 1
    return value


def _integer(data, key, minimum=1, maximum=MAX_AMOUNT, default=None):
    value = data.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f'{key} must be a whole number from {minimum} to {maximum}.')
    return value


def _text(data, key, maximum, default='', required=False):
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValidationError(f'{key} must be text of at most {maximum} characters.')
    return value.strip()


def _choice(data, key, options, default=None):
    value = data.get(key, default)
    if not isinstance(value, str) or value not in options:
        raise ValidationError(f'Choose a valid {key}.')
    return value


def _find(rows, item_id, label):
    result = next((r for r in rows if r['id'] == item_id), None)
    if result is None:
        raise NotFound(f'{label} not found.')
    return result


def _tribe(state, user_id, required=True):
    tribe = next((t for t in state['tribes'] if any(m['id'] == user_id for m in t['members'])), None)
    if tribe is None and required:
        raise ValidationError('Join a tribe during recruitment first.')
    return tribe


def _player(state, user):
    return state['players'].setdefault(
        str(user.pk), {'id': user.pk, 'username': user.username, 'inventory': {}, 'production': {}, 'experience': {}}
    )


def _log(season, tribe_id, user_id, text):
    Activity.objects.create(season=season, tribe_id=tribe_id, user_id=user_id, text=text)


def _name(item):
    return item.replace('_', ' ')


def _place(account, kind='goods', owner='their'):
    """Activity entries are read by the whole tribe ("their pack"); errors are read by the actor ("your pack")."""
    name = PLACES[kind][account]
    return f'the {name}' if account == 'tribe' else f'{owner} {name}'


def _inventory(state, tribe, user_id, account):
    return tribe['inventory'] if account == 'tribe' else state['players'][str(user_id)]['inventory']


def _items(inventory, item, amount, place=None):
    current = inventory.get(item, 0)
    if current + amount < 0:
        raise ValidationError(f'Not enough {_name(item)}{f" in {place}" if place else ""}.')
    if current + amount > MAX_TOTAL:
        raise ValidationError('Inventory limit reached.')
    inventory[item] = current + amount


def _publish(wallet):
    def publish():
        try:
            wallet.stream()
        except Exception:
            logger.exception('Could not publish Tribes wallet update for wallet %s', wallet.pk)

    transaction.on_commit(publish)


def _wallets(season, user_ids):
    if season.currency_id is None:
        season.currency = Currency.objects.filter(ticker='TNB').first()
    if season.currency is None:
        raise ValidationError('TNB is not configured yet.')
    wallets = {}
    for user_id in sorted(set(user_ids)):
        wallets[user_id], _ = Wallet.objects.get_or_create(owner_id=user_id, currency=season.currency, _for_update=True)
    return wallets


def _money(season, wallet, amount, reason):
    """Positive amount moves wallet coins into season reserve; negative pays out."""
    if amount > 0 and wallet.balance < amount:
        raise ValidationError('Not enough TNB in your wallet.')
    if wallet.balance - amount > MAX_TOTAL:
        raise ValidationError('Wallet balance limit reached.')
    if amount > 0:
        season.total_deposited += amount
    else:
        season.total_withdrawn -= amount
    if max(season.total_deposited, season.total_withdrawn) > MAX_TOTAL:
        raise ValidationError('Season payment limit reached.')
    wallet.change_balance(-amount, should_stream=False)
    MoneyEntry.objects.create(season=season, wallet=wallet, amount=amount, reason=reason)
    _publish(wallet)


def _pay(season, tribe, user_id, account, amount, wallets, reason):
    if account == 'tribe':
        if tribe['treasury'] < amount:
            raise ValidationError('Not enough TNB in the treasury.')
        tribe['treasury'] -= amount
    else:
        _money(season, wallets[user_id], amount, reason)


def _credit(season, tribe, user_id, account, amount, wallets, reason):
    if account == 'tribe':
        tribe['treasury'] += amount
    else:
        _money(season, wallets[user_id], -amount, reason)


def _conserve(season):
    held = sum(t['treasury'] for t in season.state['tribes'])
    held += sum(
        listing['quantity'] * listing['price'] for listing in season.state['listings'] if listing['kind'] == 'buy'
    )
    if season.total_deposited != season.total_withdrawn + season.system_revenue + held:
        raise RuntimeError('Tribes TNB conservation check failed.')


def _new_season(now):
    starts = now + timedelta(days=1)
    return Season.objects.create(starts_at=starts, ends_at=starts + timedelta(days=7), state=new_state())


def _lock_world():
    World.objects.get_or_create(pk=1)
    return World.objects.select_for_update().get(pk=1)


def _start(season):
    state = season.state
    count = len(state['tribes'])
    width = max(1, math.ceil(math.sqrt(count)))
    # Equal 5x5 home regions, surrounded by a one-tile border. Each region gets
    # every resource adjacent to its center, including those on map edges.
    homes = [(2 + 5 * x, 2 + 5 * y) for y in range(width) for x in range(width)]
    random.SystemRandom().shuffle(homes)
    resources = list(LAND)
    for y in range(width * 5):
        for x in range(width * 5):
            terrain = resources[(x + 2 * y) % len(resources)]
            state['plots'].append(
                {
                    'id': _id(state),
                    'x': x,
                    'y': y,
                    'terrain': terrain,
                    'tribe_id': None,
                    'price': LAND[terrain]['price'],
                    'buildings': [],
                }
            )
    by_position = {(p['x'], p['y']): p for p in state['plots']}
    offsets = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1)]
    for tribe, (x, y) in zip(state['tribes'], homes):
        home = by_position[x, y]
        home.update(tribe_id=tribe['id'], terrain='plains', price=0)
        for terrain, (dx, dy) in zip(resources, offsets):
            by_position[x + dx, y + dy].update(terrain=terrain, price=LAND[terrain]['price'])
        tribe['applications'], tribe['invites'] = [], []
        _log(season, tribe['id'], None, 'The season began. Rosters are locked and your home plot is ready.')
    players = sum(len(t['members']) for t in state['tribes'])
    for item, (per_player, price) in OPENING_STOCK.items():
        state['listings'].append(
            {
                'id': _id(state),
                'kind': 'sell',
                'item': item,
                'quantity': per_player * players,
                'price': price,
                'user_id': None,
                'tribe_id': None,
                'account': 'tribe',
            }
        )
    season.status = 'active'


def _produce(season, until):
    state = season.state
    for job in sorted(state['jobs'], key=lambda j: (j['start_at'], j['id'])):
        if job['status'] in ('completed', 'cancelled'):
            continue
        start, end = parse_datetime(job['start_at']), parse_datetime(job['end_at'])
        if until <= start:
            continue
        elapsed = (min(until, end) - start).total_seconds()
        produced = min(job['quantity'], int(elapsed * job['quantity'] / (end - start).total_seconds()))
        delta = produced - job['completed']
        tribe = _find(state['tribes'], job['tribe_id'], 'Tribe')
        if delta:
            if job['kind'] == 'build':
                plot = _find(state['plots'], job['plot_id'], 'Plot')
                plot['buildings'].append(job['item'])
            elif job['item'] in UNITS or job['item'] in DEFENSES:
                unit = next((u for u in state['units'] if u.get('job_id') == job['id']), None)
                if unit:
                    unit['quantity'] += delta
                else:
                    state['units'].append(
                        {
                            'id': _id(state),
                            'job_id': job['id'],
                            'tribe_id': tribe['id'],
                            'controller_id': job['user_id'],
                            'item': job['item'],
                            'quantity': delta,
                            'plot_id': job['plot_id'],
                            'target_id': job.get('target_id'),
                        }
                    )
            else:
                inventory = _inventory(state, tribe, job['user_id'], job['destination'])
                _items(inventory, job['item'], delta)
            player = state['players'][str(job['user_id'])]
            _items(player['production'], job['item'], delta)
            _items(player['experience'], job['item'], delta)
            for order in state['work_orders']:
                if (
                    order['tribe_id'] == tribe['id']
                    and order['item'] == job['item']
                    and order['item'] not in TRADE_ITEMS
                    and order['status'] == 'open'
                ):
                    order['contributed'] = min(order['quantity'], order['contributed'] + delta)
                    if order['contributed'] == order['quantity']:
                        order['status'] = 'completed'
                        _log(season, tribe['id'], job['user_id'], f'Completed production work order: {order["title"]}.')
            job['completed'] = produced
        job['status'] = 'completed' if until >= end else 'working'
        if job['status'] == 'completed':
            _log(season, tribe['id'], job['user_id'], f'Completed {job["quantity"]} {job["item"].replace("_", " ")}.')


def _finish(season):
    state = season.state
    state['battle'] = resolve_battle(state['tribes'], state['units'], state['plots'])
    refunds = {}
    for listing in state['listings']:
        if listing['kind'] != 'buy' or listing['quantity'] == 0:
            continue
        amount = listing['quantity'] * listing['price']
        if listing['account'] == 'tribe':
            _find(state['tribes'], listing['tribe_id'], 'Tribe')['treasury'] += amount
        else:
            refunds[listing['user_id']] = refunds.get(listing['user_id'], 0) + amount
        listing['quantity'] = 0
    for tribe in state['tribes']:
        members = sorted(m['id'] for m in tribe['members'])
        if members:
            share, remainder = divmod(tribe['treasury'], len(members))
            for index, user_id in enumerate(members):
                amount = share + int(index < remainder)
                if amount:
                    refunds[user_id] = refunds.get(user_id, 0) + amount
            tribe['treasury'] = 0
        _log(
            season,
            tribe['id'],
            None,
            'The Great War is complete. Remaining treasury TNB was divided equally among the roster.',
        )
    if refunds:
        wallets = _wallets(season, refunds)
        for user_id, amount in sorted(refunds.items()):
            _money(season, wallets[user_id], -amount, 'season_refund')
    season.status = 'finished'


def _advance(season, now):
    if season.status == 'recruiting' and now >= season.starts_at:
        _start(season)
    if season.status == 'active':
        _produce(season, min(now, season.ends_at))
        if now >= season.ends_at:
            _finish(season)
    _conserve(season)
    season.save()


@transaction.atomic
def tick_world():
    _lock_world()
    now = timezone.now()
    season = Season.objects.select_for_update().order_by('-id').first()
    if season is None:
        season = _new_season(now)
    _advance(season, now)
    if season.status == 'finished':
        season = _new_season(now)
    return season.pk


def season_summary(season):
    return {
        'id': season.pk,
        'status': season.status,
        'starts_at': season.starts_at.isoformat(),
        'ends_at': season.ends_at.isoformat(),
    }


def _media_url(name, request=None):
    """Public address of a stored upload, or None when nothing was uploaded."""
    if not name:
        return None
    url = default_storage.url(name)
    return request.build_absolute_uri(url) if request else url


def _avatars(user_ids, request=None):
    """Current avatars by user ID. The season only stores IDs and names, so a new avatar shows at once."""
    wanted = {user_id for user_id in user_ids if user_id is not None}
    rows = User.objects.filter(pk__in=wanted).exclude(avatar='').values_list('pk', 'avatar')
    return {user_id: _media_url(name, request) for user_id, name in rows}


def _serialize(season, user, request=None):
    state = copy.deepcopy(season.state)
    user_id = user.pk if user is not None and user.is_authenticated else None
    own = _tribe(state, user_id, required=False)
    own_id = own['id'] if own else None
    invitations, applications = [], []
    for tribe in state['tribes']:
        tribe['emblem_image'] = _media_url(tribe.get('emblem_image'), request)
        if any(m['id'] == user_id for m in tribe['invites']):
            invitations.append({'tribe_id': tribe['id'], 'name': tribe['name']})
        if any(m['id'] == user_id for m in tribe['applications']):
            applications.append({'tribe_id': tribe['id'], 'name': tribe['name']})
        if tribe['id'] != own_id:
            tribe['treasury'], tribe['inventory'] = None, None
        if tribe['founder_id'] != user_id:
            tribe['applications'], tribe['invites'] = [], []
    plots = {p['id']: p for p in state['plots']}
    for unit in state['units']:
        unit.pop('job_id', None)
        if unit['tribe_id'] != own_id and season.status != 'finished':
            unit.pop('target_id', None)
        unit['valid_target_ids'] = []
        if unit['item'] in UNITS:
            unit['valid_target_ids'] = sorted(
                {
                    p['tribe_id']
                    for p in state['plots']
                    if p['tribe_id'] is not None
                    and p['tribe_id'] != unit['tribe_id']
                    and distance(plots[unit['plot_id']], p) <= UNITS[unit['item']]['range']
                }
            )
    jobs = [
        j
        for j in state['jobs']
        if j['tribe_id'] == own_id
        or ((j['item'] in UNITS or j['item'] in DEFENSES) and j['status'] not in ('cancelled', 'completed'))
    ]
    for job in jobs:
        job.pop('inputs', None)
        if job['tribe_id'] != own_id and season.status != 'finished':
            job.pop('target_id', None)
    messages = [m for m in state['messages'] if own_id is not None and own_id in (m['from_tribe_id'], m['to_tribe_id'])]
    messages = messages[-200:]
    activity = []
    if own:
        activity = [
            {
                'id': a.pk,
                'tribe_id': a.tribe_id,
                'user_id': a.user_id,
                'username': a.user.username if a.user else 'Tribes',
                'text': a.text,
                'created_at': a.created_at.isoformat(),
            }
            for a in season.activity.filter(tribe_id=own_id).select_related('user').order_by('-id')[:200]
        ]
    people = [m for t in state['tribes'] for group in ('members', 'applications', 'invites') for m in t[group]]
    avatars = _avatars(
        [p['id'] for p in people] + [row['user_id'] for row in (*messages, *activity)] + [user_id], request
    )
    for row in people:
        row['avatar'] = avatars.get(row['id'])
    for row in (*messages, *activity):
        row['avatar'] = avatars.get(row['user_id'])
    viewer = None
    if user_id:
        player = state['players'].get(
            str(user_id),
            {'id': user_id, 'username': user.username, 'inventory': {}, 'production': {}, 'experience': {}},
        )
        wallet = Wallet.objects.filter(owner_id=user_id, currency__ticker='TNB').first()
        viewer = {
            **player,
            'avatar': avatars.get(user_id),
            'tribe_id': own_id,
            'wallet_balance': wallet.balance if wallet else 0,
        }
    return {
        'season': season_summary(season),
        'server_time': timezone.now().isoformat(),
        'catalog': catalog(),
        'viewer': viewer,
        'tribes': state['tribes'],
        'invitations': invitations,
        'applications': applications,
        'plots': state['plots'],
        'jobs': [j for j in jobs if j['tribe_id'] == own_id and j['status'] in ('working', 'queued')]
        + [j for j in jobs if not (j['tribe_id'] == own_id and j['status'] in ('working', 'queued'))][-500:],
        'units': state['units'],
        'listings': [listing for listing in state['listings'] if listing['quantity'] > 0],
        'messages': messages,
        'work_orders': [w for w in state['work_orders'] if w['tribe_id'] == own_id],
        'activity': activity,
        'battle': state['battle'],
    }


def get_state(user=None, season_id=None, request=None):
    current_id = tick_world()
    try:
        season = Season.objects.get(pk=season_id or current_id)
    except (Season.DoesNotExist, ValueError, TypeError):
        raise NotFound('Season not found.')
    return _serialize(season, user, request)


def _recruit(season, user, action, data):
    state = season.state
    tribe = _tribe(state, user.pk, required=False)
    if action == 'create_tribe':
        if tribe:
            raise ValidationError('You already belong to a tribe.')
        tribe = {
            'id': _id(state),
            'name': '',
            'emblem': '🛡️',
            'emblem_image': None,
            'color': '#46634a',
            'description': '',
            'motto': '',
            'founder_id': user.pk,
            'members': [{'id': user.pk, 'username': user.username}],
            'treasury': 0,
            'inventory': {},
            'applications': [],
            'invites': [],
        }
        state['tribes'].append(tribe)
        _player(state, user)
    if action in ('create_tribe', 'update_tribe'):
        if not tribe or tribe['founder_id'] != user.pk:
            raise PermissionDenied('Only the founder can edit recruitment details.')
        name = _text(data, 'name', 40, required=True)
        if any(t['id'] != tribe['id'] and t['name'].casefold() == name.casefold() for t in state['tribes']):
            raise ValidationError('A tribe already uses this name.')
        tribe.update(
            name=name,
            emblem=_text(data, 'emblem', 8, tribe['emblem']),
            description=_text(data, 'description', 500),
            motto=_text(data, 'motto', 120),
            color=_text(data, 'color', 7, '#46634a'),
        )
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', tribe['color']):
            raise ValidationError('Choose a six-digit hex tribe color.')
    elif action in ('apply', 'accept_invite'):
        if tribe:
            raise ValidationError('Leave your current tribe first.')
        target = _find(state['tribes'], _integer(data, 'tribe_id'), 'Tribe')
        member = {'id': user.pk, 'username': user.username}
        if action == 'apply':
            if not any(m['id'] == user.pk for m in target['applications']):
                target['applications'].append(member)
        else:
            if not any(m['id'] == user.pk for m in target['invites']):
                raise PermissionDenied('This tribe has not invited you.')
            _join(state, target, user)
        tribe = target
    elif action in ('invite', 'accept_application', 'remove_member'):
        if not tribe or tribe['founder_id'] != user.pk:
            raise PermissionDenied('Only the founder can manage recruitment.')
        if action == 'invite':
            target = User.objects.filter(
                username__iexact=_text(data, 'username', 150, required=True), is_active=True
            ).first()
            if target is None:
                raise NotFound('Player not found.')
            if _tribe(state, target.pk, False):
                raise ValidationError('That player already belongs to a tribe.')
            if not any(m['id'] == target.pk for m in tribe['invites']):
                tribe['invites'].append({'id': target.pk, 'username': target.username})
        else:
            target_id = _integer(data, 'user_id')
            if action == 'accept_application':
                if not any(m['id'] == target_id for m in tribe['applications']):
                    raise ValidationError('No application from that player.')
                target = User.objects.filter(pk=target_id, is_active=True).first()
                if target is None:
                    raise ValidationError('Player is unavailable.')
                _join(state, tribe, target)
            else:
                if target_id == user.pk:
                    raise ValidationError('Use Leave to leave your tribe.')
                if not any(m['id'] == target_id for m in tribe['members']):
                    raise ValidationError('Player is not a member.')
                tribe['members'] = [m for m in tribe['members'] if m['id'] != target_id]
    elif action == 'leave':
        if not tribe:
            raise ValidationError('You do not belong to a tribe.')
        if tribe['founder_id'] == user.pk and len(tribe['members']) > 1:
            raise ValidationError('The founder can leave only after other members have left.')
        tribe['members'] = [m for m in tribe['members'] if m['id'] != user.pk]
        if not tribe['members']:
            state['tribes'].remove(tribe)
    else:
        raise ValidationError('Unknown recruitment action.')
    if tribe:
        _log(season, tribe['id'], user.pk, action.replace('_', ' ').capitalize() + '.')


def _join(state, tribe, user):
    if _tribe(state, user.pk, False):
        raise ValidationError('Player already belongs to a tribe.')
    if len(tribe['members']) >= MAX_MEMBERS:
        raise ValidationError('This tribe already has eight members.')
    tribe['members'].append({'id': user.pk, 'username': user.username})
    for other in state['tribes']:
        other['applications'] = [m for m in other['applications'] if m['id'] != user.pk]
        other['invites'] = [m for m in other['invites'] if m['id'] != user.pk]
    _player(state, user)


def _owned_plot(state, tribe_id, plot_id):
    plot = _find(state['plots'], plot_id, 'Plot')
    if plot['tribe_id'] != tribe_id:
        raise ValidationError('Choose a plot owned by this tribe.')
    return plot


def _placement(state, plot_id, quantity, exclude_unit=None):
    used = sum(u['quantity'] for u in state['units'] if u['plot_id'] == plot_id and u['id'] != exclude_unit)
    used += sum(
        j['quantity'] - j['completed']
        for j in state['jobs']
        if j['plot_id'] == plot_id
        and (j['item'] in UNITS or j['item'] in DEFENSES)
        and j['status'] not in ('cancelled', 'completed')
    )
    used += sum(
        listing['quantity'] for listing in state['listings'] if listing.get('escrow_unit', {}).get('plot_id') == plot_id
    )
    if used + quantity > UNIT_CAPACITY:
        raise ValidationError(
            f'This plot can hold at most {UNIT_CAPACITY} military units and defenses, including queued production.'
        )


def _queue(season, tribe, user, data, now):
    state = season.state
    kind = _choice(data, 'kind', ('gather', 'craft', 'build'))
    plot = _owned_plot(state, tribe['id'], _integer(data, 'plot_id'))
    source = _choice(data, 'source', ('personal', 'tribe'), 'tribe')
    destination = _choice(data, 'destination', ('personal', 'tribe'), 'tribe')
    pending = [j for j in state['jobs'] if j['user_id'] == user.pk and j['status'] not in ('cancelled', 'completed')]
    start = max([now] + [parse_datetime(j['end_at']) for j in pending])
    inputs = {}
    if kind == 'gather':
        item = LAND[plot['terrain']]['resource']
        hours = _integer(data, 'hours', 1, 12)
        player = state['players'][str(user.pk)]
        rate = 10 + min(5, player['experience'].get(item, 0) // 100)
        tool = 'axe' if item == 'timber' else ('pickaxe' if item in ('iron_ore', 'coal', 'stone') else None)
        if tool and (player['inventory'].get(tool, 0) or tribe['inventory'].get(tool, 0)):
            rate += 5
        if any(
            b in plot['buildings']
            for b in BUILDINGS
            if item == BUILDINGS[b]['resource']
            or (BUILDINGS[b]['resource'] == 'mining' and item in ('iron_ore', 'coal'))
        ):
            rate += 10
        quantity, seconds = rate * hours, hours * 3600
    else:
        item = _choice(data, 'item', BUILDINGS if kind == 'build' else [r for r in RECIPES if r not in BUILDINGS])
        quantity = 1 if kind == 'build' else _integer(data, 'quantity', 1, 1000)
        recipe = RECIPES[item]
        seconds = recipe['seconds'] * quantity
        if recipe['facility'] and not any(
            recipe['facility'] in p['buildings'] for p in state['plots'] if p['tribe_id'] == tribe['id']
        ):
            raise ValidationError(f'Build a {recipe["facility"]} before manufacturing this item.')
        if kind == 'build':
            reserved = [
                j
                for j in state['jobs']
                if j['plot_id'] == plot['id'] and j['kind'] == 'build' and j['status'] not in ('cancelled', 'completed')
            ]
            if plot['terrain'] not in BUILDINGS[item]['land']:
                raise ValidationError('That building cannot be constructed on this terrain.')
            if item in plot['buildings'] or any(j['item'] == item for j in reserved):
                raise ValidationError('This building already exists or is queued on this plot.')
            if len(plot['buildings']) + len(reserved) >= BUILDING_CAPACITY:
                raise ValidationError('This plot has reached its building capacity.')
        if item in UNITS or item in DEFENSES:
            _placement(state, plot['id'], quantity)
        inputs = recipe['inputs']
        inventory = _inventory(state, tribe, user.pk, source)
        for ingredient, amount in inputs.items():
            _items(inventory, ingredient, -amount * quantity, _place(source, owner='your'))
    end = start + timedelta(seconds=seconds)
    if end > now + timedelta(seconds=QUEUE_SECONDS):
        raise ValidationError('Your worker queue cannot exceed 24 hours.')
    if end > season.ends_at:
        raise ValidationError('This assignment would finish after the final battle.')
    if kind == 'gather':
        overlaps = [
            j
            for j in state['jobs']
            if j['kind'] == 'gather'
            and j['plot_id'] == plot['id']
            and j['status'] not in ('cancelled', 'completed')
            and parse_datetime(j['start_at']) < end
            and parse_datetime(j['end_at']) > start
        ]
        # Sweep interval endpoints rather than counting all overlapping bookings.
        events = [(start, 1), (end, -1)]
        for other in overlaps:
            events.extend(
                [(max(start, parse_datetime(other['start_at'])), 1), (min(end, parse_datetime(other['end_at'])), -1)]
            )
        occupancy = 0
        for _, change in sorted(events):
            occupancy += change
            if occupancy > GATHER_CAPACITY:
                raise ValidationError('This deposit already has five workers during that time.')
    target_id = data.get('target_id')
    if target_id is not None:
        target_id = _integer(data, 'target_id')
        if (
            item not in UNITS
            or target_id == tribe['id']
            or not any(p['tribe_id'] == target_id and distance(plot, p) <= UNITS[item]['range'] for p in state['plots'])
        ):
            raise ValidationError('That tribe is outside the queued unit’s attack range.')
    job = {
        'id': _id(state),
        'user_id': user.pk,
        'tribe_id': tribe['id'],
        'kind': kind,
        'item': item,
        'quantity': quantity,
        'completed': 0,
        'plot_id': plot['id'],
        'start_at': start.isoformat(),
        'end_at': end.isoformat(),
        'status': 'working' if start <= now else 'queued',
        'source': source,
        'destination': destination,
        'inputs': inputs,
        'target_id': target_id,
    }
    state['jobs'].append(job)
    bound = '' if item in BUILDINGS or item in UNITS or item in DEFENSES else f' for {_place(destination)}'
    _log(season, tribe['id'], user.pk, f'Queued {quantity} {_name(item)} ({kind}){bound}.')


def _cancel_job(season, tribe, user, data):
    job = _find(season.state['jobs'], _integer(data, 'job_id'), 'Job')
    if job['user_id'] != user.pk:
        raise PermissionDenied('Only the worker can cancel their assignment.')
    if job['status'] in ('completed', 'cancelled'):
        raise ValidationError('That assignment is no longer active.')
    inventory = _inventory(season.state, tribe, user.pk, job['source'])
    for item, amount in job['inputs'].items():
        _items(inventory, item, amount * (job['quantity'] - job['completed']))
    job['status'] = 'cancelled'
    # Keep later reservations at their advertised times; shifting would violate
    # other workers' gathering-capacity reservations. They can be cancelled too.
    returned = f' and unused materials went back to {_place(job["source"])}' if job['inputs'] else ''
    _log(season, tribe['id'], user.pk, f'Cancelled an assignment; completed work was kept{returned}.')


def _restore_units(state, listing, tribe_id, controller_id, plot_id, quantity):
    _owned_plot(state, tribe_id, plot_id)
    _placement(state, plot_id, quantity)
    state['units'].append(
        {
            'id': _id(state),
            'tribe_id': tribe_id,
            'controller_id': controller_id,
            'item': listing['item'],
            'quantity': quantity,
            'plot_id': plot_id,
            'target_id': None,
        }
    )


def _trade(season, tribe, user, action, data):
    state = season.state
    if action == 'create_listing':
        kind = _choice(data, 'kind', ('sell', 'buy'))
        item = _choice(data, 'item', [*TRADE_ITEMS, *UNITS, *DEFENSES])
        quantity = _integer(data, 'quantity', 1, 1_000_000)
        price = _integer(data, 'price', 1, 1_000_000)
        account = _choice(data, 'account', ('personal', 'tribe'), 'personal')
        if (
            len([listing for listing in state['listings'] if listing['user_id'] == user.pk and listing['quantity'] > 0])
            >= 50
        ):
            raise ValidationError('You can have at most 50 open listings.')
        escrow_unit = None
        if item in UNITS or item in DEFENSES:
            if kind != 'sell':
                raise ValidationError('Military units can be sold directly; buy orders are for materials and tools.')
            unit = _find(state['units'], _integer(data, 'unit_id'), 'Unit')
            if unit['controller_id'] != user.pk or unit['tribe_id'] != tribe['id']:
                raise PermissionDenied('Only the controller may sell these units.')
            if unit['item'] != item or unit['quantity'] < quantity:
                raise ValidationError('Choose a matching unit batch with enough units.')
            escrow_unit = {'controller_id': user.pk, 'plot_id': unit['plot_id']}
            unit['quantity'] -= quantity
            unit.pop('job_id', None)
            if unit['quantity'] == 0:
                state['units'].remove(unit)
        elif kind == 'sell':
            _items(_inventory(state, tribe, user.pk, account), item, -quantity, _place(account, owner='your'))
        else:
            wallets = _wallets(season, [user.pk]) if account == 'personal' else {}
            _pay(season, tribe, user.pk, account, quantity * price, wallets, 'buy_order_escrow')
        listing = {
            'id': _id(state),
            'kind': kind,
            'item': item,
            'quantity': quantity,
            'price': price,
            'user_id': user.pk,
            'tribe_id': tribe['id'],
            'account': account,
        }
        if escrow_unit:
            listing['escrow_unit'] = escrow_unit
        state['listings'].append(listing)
        if kind == 'buy':
            terms = f'paid from {_place(account, "tnb")}'
        elif escrow_unit:
            terms = f'paid into {_place(account, "tnb")}'
        else:
            terms = f'from {_place(account)}'
        _log(
            season,
            tribe['id'],
            user.pk,
            f'Listed {kind} order #{listing["id"]}: {quantity} {_name(item)} at {price} TNB each, {terms}.',
        )
        return
    listing = _find(state['listings'], _integer(data, 'listing_id'), 'Listing')
    if listing['quantity'] == 0:
        raise ValidationError('This listing is already closed.')
    owner_tribe = _find(state['tribes'], listing['tribe_id'], 'Tribe') if listing['user_id'] else None
    if action == 'cancel_listing':
        if listing['user_id'] != user.pk:
            raise PermissionDenied('Only the creator can cancel this listing.')
        quantity = listing['quantity']
        listing['quantity'] = 0
        if listing.get('escrow_unit'):
            _restore_units(state, listing, tribe['id'], user.pk, listing['escrow_unit']['plot_id'], quantity)
        elif listing['kind'] == 'sell':
            _items(_inventory(state, owner_tribe, user.pk, listing['account']), listing['item'], quantity)
        else:
            wallets = _wallets(season, [user.pk]) if listing['account'] == 'personal' else {}
            _credit(
                season,
                owner_tribe,
                user.pk,
                listing['account'],
                quantity * listing['price'],
                wallets,
                'buy_order_refund',
            )
        if listing.get('escrow_unit'):
            returned = 'units returned to their plot'
        elif listing['kind'] == 'sell':
            returned = f'goods returned to {_place(listing["account"])}'
        else:
            returned = f'TNB returned to {_place(listing["account"], "tnb")}'
        _log(
            season,
            tribe['id'],
            user.pk,
            f'Cancelled order #{listing["id"]}: {quantity} {_name(listing["item"])} at {listing["price"]} TNB each; {returned}.',
        )
        return
    if listing['user_id'] == user.pk or (listing['account'] == 'tribe' and listing['tribe_id'] == tribe['id']):
        raise ValidationError(
            'You cannot fill your own listing, or one placed from your tribe’s warehouse or treasury.'
        )
    quantity = _integer(data, 'quantity', 1, listing['quantity'])
    account = _choice(data, 'account', ('personal', 'tribe'), 'personal')
    amount = quantity * listing['price']
    owner_account = listing['account']
    ids = [user.pk] if account == 'personal' else []
    if listing['user_id'] and owner_account == 'personal':
        ids.append(listing['user_id'])
    wallets = _wallets(season, ids) if ids else {}
    listing['quantity'] -= quantity
    if listing['kind'] == 'sell':
        _pay(season, tribe, user.pk, account, amount, wallets, 'market_purchase')
        if listing.get('escrow_unit'):
            _restore_units(state, listing, tribe['id'], user.pk, _integer(data, 'plot_id'), quantity)
        else:
            _items(_inventory(state, tribe, user.pk, account), listing['item'], quantity)
        if listing['user_id'] is None:
            season.system_revenue += amount
        else:
            _credit(season, owner_tribe, listing['user_id'], owner_account, amount, wallets, 'market_sale')
    else:
        _items(_inventory(state, tribe, user.pk, account), listing['item'], -quantity, _place(account, owner='your'))
        _items(_inventory(state, owner_tribe, listing['user_id'], owner_account), listing['item'], quantity)
        _credit(season, tribe, user.pk, account, amount, wallets, 'buy_order_filled')
    counterparty = owner_tribe['name'] if owner_tribe else 'the opening market'
    name = _name(listing['item'])
    # Whoever fills a sell order pays; whoever fills a buy order is paid. The order's owner is on the other side.
    selling = listing['kind'] == 'sell'
    _log(
        season,
        tribe['id'],
        user.pk,
        f'Filled order #{listing["id"]} with {counterparty}: {quantity} {name} at {listing["price"]} TNB each '
        f'({amount} TNB {"paid from" if selling else "paid into"} {_place(account, "tnb")}).',
    )
    if owner_tribe:
        _log(
            season,
            owner_tribe['id'],
            user.pk,
            f'Order #{listing["id"]} filled by {tribe["name"]}: {quantity} {name} for {amount} TNB '
            f'({"paid into" if selling else "paid from"} {_place(owner_account, "tnb", "the owner’s")}).',
        )


def _active_action(season, tribe, user, action, data, now):
    state = season.state
    if action in ('treasury_deposit', 'treasury_withdraw'):
        amount = _integer(data, 'amount')
        wallet = _wallets(season, [user.pk])[user.pk]
        if action == 'treasury_deposit':
            _money(season, wallet, amount, action)
            tribe['treasury'] += amount
        else:
            if tribe['treasury'] < amount:
                raise ValidationError('Not enough TNB in the treasury.')
            tribe['treasury'] -= amount
            _money(season, wallet, -amount, action)
        if action == 'treasury_deposit':
            _log(season, tribe['id'], user.pk, f'Deposited {amount} TNB from their wallet into the treasury.')
        else:
            _log(season, tribe['id'], user.pk, f'Withdrew {amount} TNB from the treasury into their wallet.')
    elif action == 'purchase_land':
        plot = _find(state['plots'], _integer(data, 'plot_id'), 'Plot')
        if plot['tribe_id'] is not None:
            raise ValidationError('This land is already owned.')
        if not any(p['tribe_id'] == tribe['id'] and distance(p, plot) == 1 for p in state['plots']):
            raise ValidationError('New land must be adjacent to your existing territory.')
        _pay(season, tribe, user.pk, 'tribe', plot['price'], {}, 'land_purchase')
        season.system_revenue += plot['price']
        plot['tribe_id'] = tribe['id']
        _log(season, tribe['id'], user.pk, f'Purchased land ({plot["x"]}, {plot["y"]}) for {plot["price"]} TNB.')
    elif action == 'queue':
        _queue(season, tribe, user, data, now)
    elif action == 'cancel_job':
        _cancel_job(season, tribe, user, data)
    elif action in ('create_listing', 'fill_listing', 'cancel_listing'):
        _trade(season, tribe, user, action, data)
    elif action == 'transfer_items':
        item = _choice(data, 'item', TRADE_ITEMS)
        quantity = _integer(data, 'quantity', 1, 1_000_000)
        source = _choice(data, 'source', ('personal', 'tribe'), 'personal')
        destination = _choice(data, 'destination', ('personal', 'tribe'), 'tribe')
        recipient_id = _integer(data, 'recipient_user_id', default=user.pk)
        recipient_tribe_id = _integer(data, 'recipient_tribe_id', default=tribe['id'])
        recipient_tribe = _find(state['tribes'], recipient_tribe_id, 'Tribe')
        if destination == 'personal' and (
            recipient_tribe_id != tribe['id'] or not any(m['id'] == recipient_id for m in tribe['members'])
        ):
            raise ValidationError('Goods can go into a pack only when it is yours or a teammate’s.')
        _items(_inventory(state, tribe, user.pk, source), item, -quantity, _place(source, owner='your'))
        _items(_inventory(state, recipient_tribe, recipient_id, destination), item, quantity)
        goods = f'{quantity} {_name(item)} from {_place(source)}'
        if recipient_tribe_id != tribe['id']:
            _log(season, tribe['id'], user.pk, f'Sent {goods} to {recipient_tribe["name"]}.')
            _log(
                season,
                recipient_tribe_id,
                user.pk,
                f'Sent {quantity} {_name(item)} from {tribe["name"]} into the warehouse.',
            )
        elif destination == 'tribe':
            _log(season, tribe['id'], user.pk, f'Stored {goods} in the warehouse.')
        elif recipient_id == user.pk:
            _log(season, tribe['id'], user.pk, f'Took {goods} into their pack.')
        else:
            recipient = next(member for member in tribe['members'] if member['id'] == recipient_id)
            _log(season, tribe['id'], user.pk, f'Gave {goods} to {recipient["username"]}.')
    elif action == 'transfer_tnb':
        amount = _integer(data, 'amount')
        target = _find(state['tribes'], _integer(data, 'recipient_tribe_id'), 'Tribe')
        _pay(season, tribe, user.pk, 'tribe', amount, {}, 'tribal_transfer')
        target['treasury'] += amount
        _log(season, tribe['id'], user.pk, f'Sent {amount} TNB from the treasury to {target["name"]}.')
        _log(season, target['id'], user.pk, f'Sent {amount} TNB from {tribe["name"]} into the treasury.')
    elif action in ('deploy', 'transfer_unit'):
        unit = _find(state['units'], _integer(data, 'unit_id'), 'Unit')
        if unit['controller_id'] != user.pk or unit['tribe_id'] != tribe['id']:
            raise PermissionDenied('Only the current controller can change this unit.')
        target_tribe = tribe
        if action == 'transfer_unit':
            recipient_id = _integer(data, 'recipient_user_id')
            target_tribe = _tribe(state, recipient_id)
        plot = _owned_plot(state, target_tribe['id'], _integer(data, 'plot_id'))
        _placement(state, plot['id'], unit['quantity'], unit['id'])
        if action == 'transfer_unit':
            unit.update(controller_id=recipient_id, tribe_id=target_tribe['id'], target_id=None, plot_id=plot['id'])
            # Detach a produced batch from its job: future completed units stay with the original worker.
            unit.pop('job_id', None)
            _log(
                season,
                target_tribe['id'],
                user.pk,
                f'Received {unit["quantity"]} {unit["item"]}; targeting control transferred to player {recipient_id}.',
            )
        else:
            target = data.get('target_id')
            if target is not None:
                target = _integer(data, 'target_id')
                if (
                    unit['item'] not in UNITS
                    or target == tribe['id']
                    or not any(
                        p['tribe_id'] == target and distance(plot, p) <= UNITS[unit['item']]['range']
                        for p in state['plots']
                    )
                ):
                    raise ValidationError('That tribe is outside this unit’s attack range.')
            unit.update(plot_id=plot['id'], target_id=target)
            unit.pop('job_id', None)
        if action == 'transfer_unit':
            recipient = next(member for member in target_tribe['members'] if member['id'] == recipient_id)
            _log(
                season,
                tribe['id'],
                user.pk,
                f'Transferred {unit["quantity"]} {unit["item"]} to {recipient["username"]} of {target_tribe["name"]} at ({plot["x"]}, {plot["y"]}); targets cleared.',
            )
        else:
            target_name = _find(state['tribes'], target, 'Tribe')['name'] if target is not None else 'unassigned'
            _log(
                season,
                tribe['id'],
                user.pk,
                f'Deployed {unit["quantity"]} {unit["item"]} at ({plot["x"]}, {plot["y"]}); target: {target_name}.',
            )
    elif action == 'create_work_order':
        item = _choice(data, 'item', [*TRADE_ITEMS, *UNITS, *DEFENSES, *BUILDINGS])
        state['work_orders'].append(
            {
                'id': _id(state),
                'tribe_id': tribe['id'],
                'title': _text(data, 'title', 120, required=True),
                'description': _text(data, 'description', 1000),
                'item': item,
                'quantity': _integer(data, 'quantity', 1, 1_000_000),
                'contributed': 0,
                'status': 'open',
            }
        )
        _log(season, tribe['id'], user.pk, 'Created a tribal work order.')
    elif action == 'cancel_work_order':
        order = _find(state['work_orders'], _integer(data, 'work_order_id'), 'Work order')
        if order['tribe_id'] != tribe['id']:
            raise PermissionDenied('This work order belongs to another tribe.')
        if order['status'] != 'open':
            raise ValidationError('This work order is no longer open.')
        if order['item'] in TRADE_ITEMS:
            _items(tribe['inventory'], order['item'], order['contributed'])
        order['status'] = 'cancelled'
        _log(season, tribe['id'], user.pk, f'Cancelled {order["title"]}; reserved materials returned to the warehouse.')
    elif action == 'contribute_work_order':
        order = _find(state['work_orders'], _integer(data, 'work_order_id'), 'Work order')
        if order['tribe_id'] != tribe['id']:
            raise PermissionDenied('This work order belongs to another tribe.')
        if order['status'] != 'open':
            raise ValidationError('This work order is no longer open.')
        if order['item'] not in TRADE_ITEMS:
            raise ValidationError(
                'Military and building work orders progress automatically as your tribe completes production.'
            )
        quantity = _integer(data, 'quantity', 1, order['quantity'] - order['contributed'])
        source = _choice(data, 'source', ('personal', 'tribe'), 'personal')
        _items(_inventory(state, tribe, user.pk, source), order['item'], -quantity, _place(source, owner='your'))
        order['contributed'] += quantity
        if order['contributed'] == order['quantity']:
            order['status'] = 'completed'
            _items(tribe['inventory'], order['item'], order['quantity'])
        _log(
            season,
            tribe['id'],
            user.pk,
            f'Contributed {quantity} {_name(order["item"])} from {_place(source)} to {order["title"]}.',
        )
    else:
        raise ValidationError('Unknown game action.')


RECRUIT_ACTIONS = {
    'create_tribe',
    'update_tribe',
    'apply',
    'invite',
    'accept_invite',
    'accept_application',
    'remove_member',
    'leave',
}


def _founded_tribe(season, user):
    if season.status == 'finished' or timezone.now() >= season.ends_at:
        raise ValidationError('This season has ended; all actions are locked.')
    tribe = _tribe(season.state, user.pk, required=False)
    if not tribe or tribe['founder_id'] != user.pk:
        raise PermissionDenied('Only the founder can change the tribe emblem.')
    return tribe


def set_emblem(user, season_id, image, request=None):
    """Make a square picture the emblem of the tribe the user founded, in any season that is still open."""
    is_valid, error = validate_image_dimensions(image, EMBLEM_IMAGE_SIZE, EMBLEM_IMAGE_SIZE)
    if not is_valid:
        raise ValidationError({'image': [error]})
    # Reading the dimensions leaves the file position at the end
    image.seek(0)
    tick_world()
    try:
        _founded_tribe(Season.objects.get(pk=season_id), user)
    except Season.DoesNotExist:
        raise NotFound('Season not found.')
    # Only a founder gets this far, and the file is stored before the world lock is taken so that a slow
    # upload never holds up other players. The founder is checked again once the season is locked.
    file = process_image(image)
    name = default_storage.save(f'images/{file.name}', file)
    with transaction.atomic():
        _lock_world()
        season = Season.objects.select_for_update().get(pk=season_id)
        tribe = _founded_tribe(season, user)
        tribe['emblem_image'] = name
        _log(season, tribe['id'], user.pk, 'Changed the tribe emblem.')
        season.save(update_fields=['state'])
        return _serialize(season, user, request)


def perform_action(user, data, request=None):
    if not isinstance(data, dict):
        raise ValidationError('Expected an action object.')
    try:
        request_id = UUID(str(data.get('request_id')))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('A valid request_id UUID is required.')
    season_id = _integer(data, 'season_id')
    action = _text(data, 'action', 40, required=True)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    tick_world()
    with transaction.atomic():
        _lock_world()
        receipt = ActionReceipt.objects.filter(actor=user, request_id=request_id).first()
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise RequestConflict()
            return _serialize(Season.objects.get(pk=receipt.season_id), user, request)
        try:
            season = Season.objects.select_for_update().get(pk=season_id)
        except Season.DoesNotExist:
            raise NotFound('Season not found.')
        now = timezone.now()
        if season.status == 'finished' or now >= season.ends_at:
            raise ValidationError('This season has ended; all actions are locked.')
        _advance(season, now)
        if action in RECRUIT_ACTIONS:
            if season.status != 'recruiting':
                raise ValidationError('Team rosters are locked during the season.')
            _recruit(season, user, action, data)
        else:
            tribe = _tribe(season.state, user.pk)
            if action == 'message':
                target = _find(season.state['tribes'], _integer(data, 'to_tribe_id', default=tribe['id']), 'Tribe')
                text = _text(data, 'text', 2000, required=True)
                last = [
                    m for m in season.state['messages'] if m['user_id'] == user.pk and m['to_tribe_id'] == target['id']
                ]
                if last and (now - parse_datetime(last[-1]['created_at'])).total_seconds() < 2:
                    raise ValidationError('Please wait a moment before sending another message.')
                season.state['messages'].append(
                    {
                        'id': _id(season.state),
                        'from_tribe_id': tribe['id'],
                        'to_tribe_id': target['id'],
                        'user_id': user.pk,
                        'username': user.username,
                        'text': text,
                        'created_at': now.isoformat(),
                    }
                )
                _log(season, tribe['id'], user.pk, f'Sent a message to {target["name"]}.')
            else:
                if season.status != 'active':
                    raise ValidationError('Production, trading and treasury TNB open when the season starts.')
                _active_action(season, tribe, user, action, data, now)
        _conserve(season)
        season.save()
        ActionReceipt.objects.create(
            season=season, actor=user, request_id=request_id, fingerprint=fingerprint, action=action
        )
        return _serialize(season, user, request)


def activity_page(user, season_id, before=None, request=None):
    try:
        season = Season.objects.get(pk=season_id)
    except Season.DoesNotExist:
        raise NotFound('Season not found.')
    tribe = _tribe(season.state, user.pk, required=False)
    if tribe is None:
        raise PermissionDenied('Activity is private to this season’s tribe members.')
    query = season.activity.filter(tribe_id=tribe['id']).select_related('user').order_by('-id')
    if before is not None:
        query = query.filter(pk__lt=before)
    rows = list(query[:101])
    results = [
        {
            'id': row.pk,
            'tribe_id': row.tribe_id,
            'user_id': row.user_id,
            'username': row.user.username if row.user else 'Tribes',
            'avatar': _media_url(row.user.avatar.name, request) if row.user else None,
            'text': row.text,
            'created_at': row.created_at.isoformat(),
        }
        for row in rows[:100]
    ]
    return {'results': results, 'next_before': results[-1]['id'] if len(rows) > 100 else None}


def messages_page(user, season_id, before=None, request=None):
    try:
        season = Season.objects.get(pk=season_id)
    except Season.DoesNotExist:
        raise NotFound('Season not found.')
    tribe = _tribe(season.state, user.pk, required=False)
    if tribe is None:
        raise PermissionDenied('Correspondence is private to this season’s tribe members.')
    rows = sorted(
        (
            message
            for message in season.state['messages']
            if tribe['id'] in (message['from_tribe_id'], message['to_tribe_id'])
            and (before is None or message['id'] < before)
        ),
        key=lambda message: message['id'],
        reverse=True,
    )
    avatars = _avatars([row['user_id'] for row in rows[:100]], request)
    results = [{**row, 'avatar': avatars.get(row['user_id'])} for row in rows[:100]]
    return {'results': results, 'next_before': results[-1]['id'] if len(rows) > 100 else None}
