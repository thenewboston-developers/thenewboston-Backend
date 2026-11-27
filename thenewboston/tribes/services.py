"""Authoritative Tribes state machine.

Tournament -> Wallet (sorted owner IDs) is the lock order. Each tournament has
its own lock; shared wallet row locks prevent spending across games twice.
Every real TNB movement has a permanent ledger entry and conservation is checked
before committing. Clients never supply balances, rates, output, or combat scores.
"""

import copy
import hashlib
import json
import logging
import math
import random
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

from .models import ActionReceipt, Activity, MoneyEntry, Tournament, TournamentParticipant
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
        raise ValidationError('An administrator must assign you to a tribe first.')
    return tribe


def _player(state, user):
    return state['players'].setdefault(
        str(user.pk), {'id': user.pk, 'username': user.username, 'inventory': {}, 'production': {}, 'experience': {}}
    )


def _log(tournament, tribe_id, user_id, text):
    Activity.objects.create(tournament=tournament, tribe_id=tribe_id, user_id=user_id, text=text)


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


def _wallets(tournament, user_ids):
    if tournament.currency_id is None:
        tournament.currency = Currency.objects.filter(ticker='TNB').first()
    if tournament.currency is None:
        raise ValidationError('TNB is not configured yet.')
    wallets = {}
    for user_id in sorted(set(user_ids)):
        wallets[user_id], _ = Wallet.objects.get_or_create(
            owner_id=user_id, currency=tournament.currency, _for_update=True
        )
    return wallets


def _money(tournament, wallet, amount, reason):
    """Positive amount moves wallet coins into tournament reserve; negative pays out."""
    if amount > 0 and wallet.balance < amount:
        raise ValidationError('Not enough TNB in your wallet.')
    if wallet.balance - amount > MAX_TOTAL:
        raise ValidationError('Wallet balance limit reached.')
    if amount > 0:
        tournament.total_deposited += amount
    else:
        tournament.total_withdrawn -= amount
    if max(tournament.total_deposited, tournament.total_withdrawn) > MAX_TOTAL:
        raise ValidationError('Tournament payment limit reached.')
    wallet.change_balance(-amount, should_stream=False)
    MoneyEntry.objects.create(tournament=tournament, wallet=wallet, amount=amount, reason=reason)
    _publish(wallet)


def _pay(tournament, tribe, user_id, account, amount, wallets, reason):
    if account == 'tribe':
        if tribe['treasury'] < amount:
            raise ValidationError('Not enough TNB in the treasury.')
        tribe['treasury'] -= amount
    else:
        _money(tournament, wallets[user_id], amount, reason)


def _credit(tournament, tribe, user_id, account, amount, wallets, reason):
    if account == 'tribe':
        tribe['treasury'] += amount
    else:
        _money(tournament, wallets[user_id], -amount, reason)


def _conserve(tournament):
    held = sum(t['treasury'] for t in tournament.state['tribes'])
    held += sum(
        listing['quantity'] * listing['price'] for listing in tournament.state['listings'] if listing['kind'] == 'buy'
    )
    if tournament.total_deposited != tournament.total_withdrawn + tournament.system_revenue + held:
        raise RuntimeError('Tribes TNB conservation check failed.')


def _start(tournament):
    state = tournament.state
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
        _log(tournament, tribe['id'], None, 'The tournament began. Rosters are locked and your home plot is ready.')
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
    tournament.status = 'active'


def _produce(tournament, until):
    state = tournament.state
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
                        _log(
                            tournament,
                            tribe['id'],
                            job['user_id'],
                            f'Completed production work order: {order["title"]}.',
                        )
            job['completed'] = produced
        job['status'] = 'completed' if until >= end else 'working'
        if job['status'] == 'completed':
            _log(
                tournament, tribe['id'], job['user_id'], f'Completed {job["quantity"]} {job["item"].replace("_", " ")}.'
            )


def _finish(tournament):
    state = tournament.state
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
            tournament,
            tribe['id'],
            None,
            'The Great War is complete. Remaining treasury TNB was divided equally among the roster.',
        )
    if refunds:
        wallets = _wallets(tournament, refunds)
        for user_id, amount in sorted(refunds.items()):
            _money(tournament, wallets[user_id], -amount, 'tournament_refund')
    tournament.status = 'finished'


def _advance(tournament, now):
    if tournament.status == 'upcoming' and now >= tournament.starts_at:
        _start(tournament)
    if tournament.status == 'active':
        _produce(tournament, min(now, tournament.ends_at))
        if now >= tournament.ends_at:
            _finish(tournament)
    _conserve(tournament)
    tournament.save()


@transaction.atomic
def advance_tournament(tournament_id):
    """Commit scheduled transitions independently of any subsequent action rejection."""
    tournament = _locked_tournament(tournament_id)
    _advance(tournament, timezone.now())
    return tournament


def sweep_tournaments():
    """A failed game must not prevent unrelated games from starting or finishing."""
    processed, failed = [], []
    for tournament_id in Tournament.objects.exclude(status='finished').order_by('id').values_list('id', flat=True):
        try:
            advance_tournament(tournament_id)
        except Exception:
            logger.exception('Could not advance Tribes tournament %s', tournament_id)
            failed.append(tournament_id)
        else:
            processed.append(tournament_id)
    return {'processed': processed, 'failed': failed}


def tournament_summary(tournament, user=None):
    user_id = user.pk if user is not None and user.is_authenticated else None
    return {
        'id': tournament.pk,
        'title': tournament.title,
        'status': tournament.status,
        'starts_at': tournament.starts_at.isoformat(),
        'ends_at': tournament.ends_at.isoformat(),
        'max_players': tournament.max_players,
        'player_count': tournament.participants.count(),
        'is_participant': bool(user_id and tournament.participants.filter(user_id=user_id).exists()),
    }


def _media_url(name, request=None):
    """Public address of a stored upload, or None when nothing was uploaded."""
    if not name:
        return None
    url = default_storage.url(name)
    return request.build_absolute_uri(url) if request else url


def _avatars(user_ids, request=None):
    """Current avatars by user ID. The tournament only stores IDs and names, so a new avatar shows at once."""
    wanted = {user_id for user_id in user_ids if user_id is not None}
    rows = User.objects.filter(pk__in=wanted).exclude(avatar='').values_list('pk', 'avatar')
    return {user_id: _media_url(name, request) for user_id, name in rows}


def _serialize(tournament, user, request=None):
    state = copy.deepcopy(tournament.state)
    user_id = user.pk if user is not None and user.is_authenticated else None
    own = _tribe(state, user_id, required=False)
    own_id = own['id'] if own else None
    for tribe in state['tribes']:
        tribe['emblem_image'] = _media_url(tribe.get('emblem_image'), request)
        if tribe['id'] != own_id:
            tribe['treasury'], tribe['inventory'] = None, None
    plots = {p['id']: p for p in state['plots']}
    for unit in state['units']:
        unit.pop('job_id', None)
        if unit['tribe_id'] != own_id and tournament.status != 'finished':
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
        if job['tribe_id'] != own_id and tournament.status != 'finished':
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
            for a in tournament.activity.filter(tribe_id=own_id).select_related('user').order_by('-id')[:200]
        ]
    people = [m for t in state['tribes'] for m in t['members']]
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
            'is_participant': tournament.participants.filter(user_id=user_id).exists(),
            'wallet_balance': wallet.balance if wallet else 0,
        }
    return {
        'tournament': tournament_summary(tournament, user),
        'server_time': timezone.now().isoformat(),
        'catalog': catalog(),
        'viewer': viewer,
        'tribes': state['tribes'],
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


def get_state(user=None, tournament_id=None, request=None):
    if tournament_id is None:
        raise ValidationError({'tournament_id': 'Select a tournament.'})
    try:
        tournament_id = int(tournament_id)
    except (ValueError, TypeError):
        raise ValidationError({'tournament_id': 'Enter a valid tournament ID.'})
    tournament = advance_tournament(tournament_id)
    return _serialize(tournament, user, request)


def _require_admin(actor, permission='change_tournament'):
    if (
        not actor
        or not actor.is_active
        or not actor.is_staff
        or not (actor.is_superuser or actor.has_perm(f'tribes.{permission}'))
    ):
        raise PermissionDenied('Tournament administration permission is required.')


def _locked_tournament(tournament_id):
    try:
        return Tournament.objects.select_for_update().get(pk=tournament_id)
    except (Tournament.DoesNotExist, ValueError, TypeError):
        raise NotFound('Tournament not found.')


def _editable_tournament(tournament_id, actor):
    _require_admin(actor)
    tournament = _locked_tournament(tournament_id)
    if tournament.status != 'upcoming' or timezone.now() >= tournament.starts_at:
        raise ValidationError('The tournament has started. Its schedule and roster are locked.')
    return tournament


def _configuration(*, title, starts_at, ends_at, max_players):
    title = _text({'title': title}, 'title', 120, required=True)
    max_players = _integer({'max_players': max_players}, 'max_players', maximum=10_000)
    if starts_at is None or timezone.is_naive(starts_at):
        raise ValidationError('Choose a start time with a time zone.')
    if starts_at <= timezone.now():
        raise ValidationError('The tournament must start in the future.')
    ends_at = ends_at or starts_at + timedelta(days=7)
    if timezone.is_naive(ends_at) or ends_at <= starts_at:
        raise ValidationError('The end time must be after the start time.')
    return {'title': title, 'starts_at': starts_at, 'ends_at': ends_at, 'max_players': max_players}


@transaction.atomic
def create_tournament(*, title, starts_at, max_players, actor, ends_at=None):
    _require_admin(actor, 'add_tournament')
    values = _configuration(title=title, starts_at=starts_at, ends_at=ends_at, max_players=max_players)
    return Tournament.objects.create(**values, state=new_state())


@transaction.atomic
def update_tournament(tournament_id, *, title, starts_at, max_players, actor, ends_at=None):
    tournament = _editable_tournament(tournament_id, actor)
    values = _configuration(title=title, starts_at=starts_at, ends_at=ends_at, max_players=max_players)
    if tournament.participants.count() > max_players:
        raise ValidationError('Capacity cannot be lower than the enrolled player count.')
    for key, value in values.items():
        setattr(tournament, key, value)
    tournament.save(update_fields=list(values))
    return tournament


def _participant(tournament, user_id):
    try:
        return tournament.participants.select_related('user').get(user_id=user_id).user
    except TournamentParticipant.DoesNotExist:
        raise ValidationError('Add this player to the tournament roster first.')


@transaction.atomic
def add_participant(tournament_id, user_id, *, actor):
    tournament = _editable_tournament(tournament_id, actor)
    if tournament.participants.filter(user_id=user_id).exists():
        return tournament
    if tournament.participants.count() >= tournament.max_players:
        raise ValidationError('This tournament is full.')
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ValidationError('Choose an active user.')
    TournamentParticipant.objects.create(tournament=tournament, user=user)
    _player(tournament.state, user)
    tournament.save(update_fields=['state'])
    return tournament


def _unassign(tournament, user_id):
    tribe = _tribe(tournament.state, user_id, required=False)
    if tribe is None:
        return
    if tribe['founder_id'] == user_id and len(tribe['members']) > 1:
        raise ValidationError('Choose a replacement captain before moving or removing this captain.')
    tribe['members'] = [member for member in tribe['members'] if member['id'] != user_id]
    if not tribe['members']:
        tournament.state['tribes'].remove(tribe)


@transaction.atomic
def remove_participant(tournament_id, user_id, *, actor):
    tournament = _editable_tournament(tournament_id, actor)
    _participant(tournament, user_id)
    _unassign(tournament, user_id)
    tournament.participants.filter(user_id=user_id).delete()
    tournament.state['players'].pop(str(user_id), None)
    tournament.save(update_fields=['state'])
    return tournament


@transaction.atomic
def create_tribe(tournament_id, *, name, founder_id, actor):
    tournament = _editable_tournament(tournament_id, actor)
    founder = _participant(tournament, founder_id)
    if _tribe(tournament.state, founder_id, required=False):
        raise ValidationError('The captain already belongs to a tribe in this tournament.')
    name = _text({'name': name}, 'name', 40, required=True)
    if any(tribe['name'].casefold() == name.casefold() for tribe in tournament.state['tribes']):
        raise ValidationError('A tribe already uses this name.')
    colors = ['#46634a', '#b65b45', '#467aaa', '#a778b8', '#b28b32', '#398b89', '#a54e7c', '#727780']
    tribe = {
        'id': _id(tournament.state),
        'name': name,
        'emblem': '🛡️',
        'emblem_image': None,
        'color': colors[len(tournament.state['tribes']) % len(colors)],
        'description': '',
        'motto': '',
        'founder_id': founder_id,
        'members': [{'id': founder.pk, 'username': founder.username}],
        'treasury': 0,
        'inventory': {},
    }
    tournament.state['tribes'].append(tribe)
    _log(tournament, tribe['id'], actor.pk, 'Created tribe and assigned its captain.')
    tournament.save(update_fields=['state'])
    return tournament


@transaction.atomic
def assign_participant(tournament_id, user_id, tribe_id, *, actor):
    tournament = _editable_tournament(tournament_id, actor)
    user = _participant(tournament, user_id)
    target = _find(tournament.state['tribes'], tribe_id, 'Tribe') if tribe_id is not None else None
    current = _tribe(tournament.state, user_id, required=False)
    if target is current:
        return tournament
    if target and len(target['members']) >= MAX_MEMBERS:
        raise ValidationError(f'A tribe can have at most {MAX_MEMBERS} members.')
    _unassign(tournament, user_id)
    if target:
        target['members'].append({'id': user.pk, 'username': user.username})
        _log(tournament, target['id'], actor.pk, f'Assigned {user.username} to the tribe.')
    tournament.save(update_fields=['state'])
    return tournament


@transaction.atomic
def set_tribe_captain(tournament_id, tribe_id, user_id, *, actor):
    tournament = _editable_tournament(tournament_id, actor)
    tribe = _find(tournament.state['tribes'], tribe_id, 'Tribe')
    if not any(member['id'] == user_id for member in tribe['members']):
        raise ValidationError('The captain must be a member of this tribe.')
    tribe['founder_id'] = user_id
    _log(tournament, tribe_id, actor.pk, 'Changed the tribe captain.')
    tournament.save(update_fields=['state'])
    return tournament


@transaction.atomic
def remove_tribe(tournament_id, tribe_id, *, actor):
    tournament = _editable_tournament(tournament_id, actor)
    tribe = _find(tournament.state['tribes'], tribe_id, 'Tribe')
    tournament.state['tribes'].remove(tribe)
    tournament.save(update_fields=['state'])
    return tournament


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


def _queue(tournament, tribe, user, data, now):
    state = tournament.state
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
    if end > tournament.ends_at:
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
    _log(tournament, tribe['id'], user.pk, f'Queued {quantity} {_name(item)} ({kind}){bound}.')


def _cancel_job(tournament, tribe, user, data):
    job = _find(tournament.state['jobs'], _integer(data, 'job_id'), 'Job')
    if job['user_id'] != user.pk:
        raise PermissionDenied('Only the worker can cancel their assignment.')
    if job['status'] in ('completed', 'cancelled'):
        raise ValidationError('That assignment is no longer active.')
    inventory = _inventory(tournament.state, tribe, user.pk, job['source'])
    for item, amount in job['inputs'].items():
        _items(inventory, item, amount * (job['quantity'] - job['completed']))
    job['status'] = 'cancelled'
    # Keep later reservations at their advertised times; shifting would violate
    # other workers' gathering-capacity reservations. They can be cancelled too.
    returned = f' and unused materials went back to {_place(job["source"])}' if job['inputs'] else ''
    _log(tournament, tribe['id'], user.pk, f'Cancelled an assignment; completed work was kept{returned}.')


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


def _trade(tournament, tribe, user, action, data):
    state = tournament.state
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
            wallets = _wallets(tournament, [user.pk]) if account == 'personal' else {}
            _pay(tournament, tribe, user.pk, account, quantity * price, wallets, 'buy_order_escrow')
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
            tournament,
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
            wallets = _wallets(tournament, [user.pk]) if listing['account'] == 'personal' else {}
            _credit(
                tournament,
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
            tournament,
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
    wallets = _wallets(tournament, ids) if ids else {}
    listing['quantity'] -= quantity
    if listing['kind'] == 'sell':
        _pay(tournament, tribe, user.pk, account, amount, wallets, 'market_purchase')
        if listing.get('escrow_unit'):
            _restore_units(state, listing, tribe['id'], user.pk, _integer(data, 'plot_id'), quantity)
        else:
            _items(_inventory(state, tribe, user.pk, account), listing['item'], quantity)
        if listing['user_id'] is None:
            tournament.system_revenue += amount
        else:
            _credit(tournament, owner_tribe, listing['user_id'], owner_account, amount, wallets, 'market_sale')
    else:
        _items(_inventory(state, tribe, user.pk, account), listing['item'], -quantity, _place(account, owner='your'))
        _items(_inventory(state, owner_tribe, listing['user_id'], owner_account), listing['item'], quantity)
        _credit(tournament, tribe, user.pk, account, amount, wallets, 'buy_order_filled')
    counterparty = owner_tribe['name'] if owner_tribe else 'the opening market'
    name = _name(listing['item'])
    # Whoever fills a sell order pays; whoever fills a buy order is paid. The order's owner is on the other side.
    selling = listing['kind'] == 'sell'
    _log(
        tournament,
        tribe['id'],
        user.pk,
        f'Filled order #{listing["id"]} with {counterparty}: {quantity} {name} at {listing["price"]} TNB each '
        f'({amount} TNB {"paid from" if selling else "paid into"} {_place(account, "tnb")}).',
    )
    if owner_tribe:
        _log(
            tournament,
            owner_tribe['id'],
            user.pk,
            f'Order #{listing["id"]} filled by {tribe["name"]}: {quantity} {name} for {amount} TNB '
            f'({"paid into" if selling else "paid from"} {_place(owner_account, "tnb", "the owner’s")}).',
        )


def _active_action(tournament, tribe, user, action, data, now):
    state = tournament.state
    if action in ('treasury_deposit', 'treasury_withdraw'):
        amount = _integer(data, 'amount')
        wallet = _wallets(tournament, [user.pk])[user.pk]
        if action == 'treasury_deposit':
            _money(tournament, wallet, amount, action)
            tribe['treasury'] += amount
        else:
            if tribe['treasury'] < amount:
                raise ValidationError('Not enough TNB in the treasury.')
            tribe['treasury'] -= amount
            _money(tournament, wallet, -amount, action)
        if action == 'treasury_deposit':
            _log(tournament, tribe['id'], user.pk, f'Deposited {amount} TNB from their wallet into the treasury.')
        else:
            _log(tournament, tribe['id'], user.pk, f'Withdrew {amount} TNB from the treasury into their wallet.')
    elif action == 'purchase_land':
        plot = _find(state['plots'], _integer(data, 'plot_id'), 'Plot')
        if plot['tribe_id'] is not None:
            raise ValidationError('This land is already owned.')
        if not any(p['tribe_id'] == tribe['id'] and distance(p, plot) == 1 for p in state['plots']):
            raise ValidationError('New land must be adjacent to your existing territory.')
        _pay(tournament, tribe, user.pk, 'tribe', plot['price'], {}, 'land_purchase')
        tournament.system_revenue += plot['price']
        plot['tribe_id'] = tribe['id']
        _log(tournament, tribe['id'], user.pk, f'Purchased land ({plot["x"]}, {plot["y"]}) for {plot["price"]} TNB.')
    elif action == 'queue':
        _queue(tournament, tribe, user, data, now)
    elif action == 'cancel_job':
        _cancel_job(tournament, tribe, user, data)
    elif action in ('create_listing', 'fill_listing', 'cancel_listing'):
        _trade(tournament, tribe, user, action, data)
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
            _log(tournament, tribe['id'], user.pk, f'Sent {goods} to {recipient_tribe["name"]}.')
            _log(
                tournament,
                recipient_tribe_id,
                user.pk,
                f'Sent {quantity} {_name(item)} from {tribe["name"]} into the warehouse.',
            )
        elif destination == 'tribe':
            _log(tournament, tribe['id'], user.pk, f'Stored {goods} in the warehouse.')
        elif recipient_id == user.pk:
            _log(tournament, tribe['id'], user.pk, f'Took {goods} into their pack.')
        else:
            recipient = next(member for member in tribe['members'] if member['id'] == recipient_id)
            _log(tournament, tribe['id'], user.pk, f'Gave {goods} to {recipient["username"]}.')
    elif action == 'transfer_tnb':
        amount = _integer(data, 'amount')
        target = _find(state['tribes'], _integer(data, 'recipient_tribe_id'), 'Tribe')
        _pay(tournament, tribe, user.pk, 'tribe', amount, {}, 'tribal_transfer')
        target['treasury'] += amount
        _log(tournament, tribe['id'], user.pk, f'Sent {amount} TNB from the treasury to {target["name"]}.')
        _log(tournament, target['id'], user.pk, f'Sent {amount} TNB from {tribe["name"]} into the treasury.')
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
                tournament,
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
                tournament,
                tribe['id'],
                user.pk,
                f'Transferred {unit["quantity"]} {unit["item"]} to {recipient["username"]} of {target_tribe["name"]} at ({plot["x"]}, {plot["y"]}); targets cleared.',
            )
        else:
            target_name = _find(state['tribes'], target, 'Tribe')['name'] if target is not None else 'unassigned'
            _log(
                tournament,
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
        _log(tournament, tribe['id'], user.pk, 'Created a tribal work order.')
    elif action == 'cancel_work_order':
        order = _find(state['work_orders'], _integer(data, 'work_order_id'), 'Work order')
        if order['tribe_id'] != tribe['id']:
            raise PermissionDenied('This work order belongs to another tribe.')
        if order['status'] != 'open':
            raise ValidationError('This work order is no longer open.')
        if order['item'] in TRADE_ITEMS:
            _items(tribe['inventory'], order['item'], order['contributed'])
        order['status'] = 'cancelled'
        _log(
            tournament,
            tribe['id'],
            user.pk,
            f'Cancelled {order["title"]}; reserved materials returned to the warehouse.',
        )
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
            tournament,
            tribe['id'],
            user.pk,
            f'Contributed {quantity} {_name(order["item"])} from {_place(source)} to {order["title"]}.',
        )
    else:
        raise ValidationError('Unknown game action.')


def _founded_tribe(tournament, user):
    if tournament.status == 'finished' or timezone.now() >= tournament.ends_at:
        raise ValidationError('This tournament has ended; all actions are locked.')
    tribe = _tribe(tournament.state, user.pk, required=False)
    if not tribe or tribe['founder_id'] != user.pk:
        raise PermissionDenied('Only the founder can change the tribe emblem.')
    return tribe


def set_emblem(user, tournament_id, image, request=None):
    """Make a square picture the emblem of the tribe the user founded, in any tournament that is still open."""
    is_valid, error = validate_image_dimensions(image, EMBLEM_IMAGE_SIZE, EMBLEM_IMAGE_SIZE)
    if not is_valid:
        raise ValidationError({'image': [error]})
    # Reading the dimensions leaves the file position at the end
    image.seek(0)
    advance_tournament(tournament_id)
    try:
        _founded_tribe(Tournament.objects.get(pk=tournament_id), user)
    except Tournament.DoesNotExist:
        raise NotFound('Tournament not found.')
    # Only a founder gets this far, and the file is stored before the tournament lock is taken so that a slow
    # upload never holds up other players. The founder is checked again once the tournament is locked.
    file = process_image(image)
    name = default_storage.save(f'images/{file.name}', file)
    with transaction.atomic():
        tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
        tribe = _founded_tribe(tournament, user)
        tribe['emblem_image'] = name
        _log(tournament, tribe['id'], user.pk, 'Changed the tribe emblem.')
        tournament.save(update_fields=['state'])
        return _serialize(tournament, user, request)


def perform_action(user, data, request=None):
    if not isinstance(data, dict):
        raise ValidationError('Expected an action object.')
    tournament_id = _integer(data, 'tournament_id')
    advance_tournament(tournament_id)
    try:
        request_id = UUID(str(data.get('request_id')))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('A valid request_id UUID is required.')
    action = _text(data, 'action', 40, required=True)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    rejection = None
    with transaction.atomic():
        tournament = _locked_tournament(tournament_id)
        now = timezone.now()
        _advance(tournament, now)
        receipt = ActionReceipt.objects.filter(tournament=tournament, actor=user, request_id=request_id).first()
        if receipt:
            if receipt.fingerprint != fingerprint:
                rejection = RequestConflict()
            else:
                return _serialize(tournament, user, request)
        else:
            # Savepoint rolls back a rejected command, while the outer transaction
            # commits start/finish if a deadline passed while waiting for the lock.
            try:
                with transaction.atomic():
                    if tournament.status == 'finished':
                        raise ValidationError('This tournament has ended; all actions are locked.')
                    if not tournament.participants.filter(user=user).exists():
                        raise PermissionDenied('You are not enrolled in this tournament.')
                    tribe = _tribe(tournament.state, user.pk)
                    _execute_action(tournament, tribe, user, action, data, now)
                    _conserve(tournament)
                    tournament.save()
                    ActionReceipt.objects.create(
                        tournament=tournament, actor=user, request_id=request_id, fingerprint=fingerprint, action=action
                    )
            except APIException as exc:
                rejection = exc
        if rejection is None:
            result = _serialize(tournament, user, request)
    if rejection is not None:
        raise rejection
    return result


def _execute_action(tournament, tribe, user, action, data, now):
    if action == 'message':
        target = _find(tournament.state['tribes'], _integer(data, 'to_tribe_id', default=tribe['id']), 'Tribe')
        text = _text(data, 'text', 2000, required=True)
        last = [m for m in tournament.state['messages'] if m['user_id'] == user.pk and m['to_tribe_id'] == target['id']]
        if last and (now - parse_datetime(last[-1]['created_at'])).total_seconds() < 2:
            raise ValidationError('Please wait a moment before sending another message.')
        tournament.state['messages'].append(
            {
                'id': _id(tournament.state),
                'from_tribe_id': tribe['id'],
                'to_tribe_id': target['id'],
                'user_id': user.pk,
                'username': user.username,
                'text': text,
                'created_at': now.isoformat(),
            }
        )
        _log(tournament, tribe['id'], user.pk, f'Sent a message to {target["name"]}.')
    else:
        if tournament.status != 'active':
            raise ValidationError('Production, trading and treasury TNB open when the tournament starts.')
        _active_action(tournament, tribe, user, action, data, now)


def activity_page(user, tournament_id, before=None, request=None):
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        raise NotFound('Tournament not found.')
    tribe = _tribe(tournament.state, user.pk, required=False)
    if tribe is None:
        raise PermissionDenied('Activity is private to this tournament’s tribe members.')
    query = tournament.activity.filter(tribe_id=tribe['id']).select_related('user').order_by('-id')
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


def messages_page(user, tournament_id, before=None, request=None):
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        raise NotFound('Tournament not found.')
    tribe = _tribe(tournament.state, user.pk, required=False)
    if tribe is None:
        raise PermissionDenied('Correspondence is private to this tournament’s tribe members.')
    rows = sorted(
        (
            message
            for message in tournament.state['messages']
            if tribe['id'] in (message['from_tribe_id'], message['to_tribe_id'])
            and (before is None or message['id'] < before)
        ),
        key=lambda message: message['id'],
        reverse=True,
    )
    avatars = _avatars([row['user_id'] for row in rows[:100]], request)
    results = [{**row, 'avatar': avatars.get(row['user_id'])} for row in rows[:100]]
    return {'results': results, 'next_before': results[-1]['id'] if len(rows) > 100 else None}
