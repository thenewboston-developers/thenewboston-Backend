import getpass
import logging
import os
import signal
import socket
import sys
import time
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Max, Min, Q, When, Window
from django.utils import timezone

from thenewboston.general.clients.redis import get_redis_client
from thenewboston.general.exceptions import ThenewbostonRuntimeError
from thenewboston.general.utils.logging import log
from thenewboston.wallets.models import Wallet

from ..models import OrderProcessingLock, Trade
from ..models.exchange_order import (
    NEW_ORDER_EVENT, ORDER_PROCESSING_LOCK_ID, SOMEWHAT_FILLED_STATUSES, UNFILLED_STATUSES, ExchangeOrder,
    ExchangeOrderSide, ExchangeOrderStatus
)

GET_MESSAGE_ITERATION_TIMEOUT_SECONDS = 1
BUY = ExchangeOrderSide.BUY.value  # type: ignore
SELL = ExchangeOrderSide.SELL.value  # type: ignore
logger = logging.getLogger(__name__)


def update_wallet(owner, currency, amount, trade_at):
    defaults = {'balance': amount, 'created_date': trade_at, 'modified_date': trade_at}
    # TODO(dmu) HIGH: If wallet is created then the balance update is not stream. It would be more consistent to
    #                 actually stream it because balance was changed from nothing to something particular
    wallet, is_created = Wallet.objects.get_or_create(
        owner=owner, currency=currency, defaults=defaults, _for_update=True
    )
    if not is_created:
        defaults.pop('balance', None)
        for attr, value in defaults.items():
            setattr(wallet, attr, value)

        wallet.change_balance(amount, should_adjust_timestamps=False)

    return wallet


def advance_to_next_pair(current_index: int, potentially_matching_orders: list[ExchangeOrder]) -> int | None:
    original_order = potentially_matching_orders[current_index]
    original_order_side = original_order.side
    original_pair = original_order.get_pair_ids()

    direction = -original_order.side  # move forward for the SELL orders, because they are on the top
    assert direction in (-1, 1)
    total_orders = len(potentially_matching_orders)

    current_index += direction
    while 0 <= current_index < total_orders:  # we should exist earlier (being defensive here)
        current_order = potentially_matching_orders[current_index]
        if current_order.side != original_order_side:
            return None  # we hit another order side that means that we have exhausted matching orders

        if current_order.get_pair_ids() != original_pair:
            return current_index

        # TODO(dmu) LOW: Linear search should be perfectly fine here since we do not expect more than several
        #                orders per currency pair per iteration. But potentially we can switch to binary-like
        #                search if this assumption appear to be wrong
        current_index += direction

    return None  # making mypy happy


def make_trade(sell_order, buy_order, trade_at):
    trade_price = sell_order.price
    overpay_price = buy_order.price - trade_price
    assert overpay_price >= 0  # covers `assert sell_order.price <= buy_order.price`

    filled_quantity = min(sell_order.unfilled_quantity, buy_order.unfilled_quantity)
    sell_order.fill_order(filled_quantity)
    assert sell_order.status in SOMEWHAT_FILLED_STATUSES
    buy_order.fill_order(filled_quantity)
    assert buy_order.status in SOMEWHAT_FILLED_STATUSES

    assert sell_order.unfilled_quantity == 0 or buy_order.unfilled_quantity == 0
    assert (
        sell_order.status == ExchangeOrderStatus.FILLED.value or buy_order.status == ExchangeOrderStatus.FILLED.value
    )

    overpayment_amount = overpay_price * filled_quantity

    # TODO(dmu) MEDIUM: Figure out the best order of saving trade, wallet and orders updates, because it affects
    #                   the order of events being streamed to the clients
    Trade(
        buy_order=buy_order,
        sell_order=sell_order,
        filled_quantity=filled_quantity,
        price=trade_price,
        overpayment_amount=overpayment_amount,
        created_date=trade_at,
        modified_date=trade_at,
    ).save(should_adjust_timestamps=False)

    buy_order_owner = buy_order.owner
    update_wallet(buy_order_owner, buy_order.primary_currency, filled_quantity, trade_at)
    if overpayment_amount:
        assert overpayment_amount > 0
        update_wallet(buy_order_owner, buy_order.secondary_currency, overpayment_amount, trade_at)

    update_wallet(sell_order.owner, sell_order.secondary_currency, trade_price * filled_quantity, trade_at)

    buy_order.modified_date = trade_at
    buy_order.save(should_adjust_timestamps=False)
    sell_order.modified_date = trade_at
    sell_order.save(should_adjust_timestamps=False)


@log(logger_=logger, level=logging.DEBUG)
def get_potentially_matching_orders(trade_at):
    return list(
        ExchangeOrder.objects.filter(fill_status__in=UNFILLED_STATUSES, created_date__lte=trade_at).annotate(
            best_ask=Window(
                expression=Min('price', filter=Q(side=SELL)),
                partition_by=('primary_currency_id', 'secondary_currency_id'),
            ),
            best_bid=Window(
                expression=Max('price', filter=Q(side=BUY)),
                partition_by=('primary_currency_id', 'secondary_currency_id'),
            ),
        ).filter(Q(side=BUY, price__gte=F('best_ask')) | Q(side=SELL, price__lte=F('best_bid'))).annotate(
            # Make SELL and BUY orders currencies go in reverse direction, so we can iterate one from top
            # and the other one from bottom
            sort_primary_currency_id=Case(
                When(side=SELL, then=F('primary_currency_id')),
                When(side=BUY, then=-F('primary_currency_id')),
                output_field=IntegerField(),
            ),
            sort_secondary_currency_id=Case(
                When(side=SELL, then=F('secondary_currency_id')),
                When(side=BUY, then=-F('secondary_currency_id')),
                output_field=IntegerField(),
            ),
        ).with_advisory_lock(ORDER_PROCESSING_LOCK_ID).order_by(
            'side',  # SELL will be first, then BUY
            'sort_primary_currency_id',
            'sort_secondary_currency_id',
            'price',  # lowest ask first (best sell goes first), then highest bid (best buy goes last)
            'created_date',
            'id',  # for stable ordering in case of exactly equal created_date
        )
    )


def find_matching_orders(sell_index, buy_index, potentially_matching_orders) -> list[int] | None:
    while sell_index is not None and buy_index is not None and sell_index < buy_index:
        sell_order = potentially_matching_orders[sell_index]
        if sell_order.side == BUY:  # no more sell orders
            break

        buy_order = potentially_matching_orders[buy_index]
        if buy_order.side == SELL:  # no more buy orders
            break

        sell_order_pair = sell_order.get_pair_ids()
        assert isinstance(sell_order_pair[0], int) and isinstance(sell_order_pair[1], int)
        buy_order_pair = buy_order.get_pair_ids()
        assert isinstance(buy_order_pair[0], int) and isinstance(buy_order_pair[1], int)

        if sell_order_pair > buy_order_pair:  # catch up currency pair for the buy orders
            buy_index = advance_to_next_pair(buy_index, potentially_matching_orders)
            continue
        elif sell_order_pair < buy_order_pair:  # catch up currency pair for the sell orders
            sell_index = advance_to_next_pair(sell_index, potentially_matching_orders)
            continue

        assert sell_order_pair == buy_order_pair
        if sell_order.price > buy_order.price:  # there is no match let's go to another currency pair
            buy_index = advance_to_next_pair(buy_index, potentially_matching_orders)
            sell_index = advance_to_next_pair(sell_index, potentially_matching_orders)
            continue

        return [sell_index, buy_index]  # we found a pair of orders that can be matched

    return None


def match_orders(potentially_matching_orders, trade_at):
    unlocked_orders = set()
    matching_indexes = find_matching_orders(0, len(potentially_matching_orders) - 1, potentially_matching_orders)
    while matching_indexes:
        assert len(matching_indexes) == 2

        # This is important that we are not in transaction, so every trade results into saving data to the database
        # and streaming events to the clients
        assert not transaction.get_connection().in_atomic_block

        with transaction.atomic():
            # TODO(dmu) LOW: We might not really need to select_for_update() here, because advisory locks are used,
            #                but we still might need to re-fetch orders, because `modified_date` is modified
            #                in make_trade() with raw SQL query
            sell_order = potentially_matching_orders[matching_indexes[0]].select_for_update()  # sell index
            buy_order = potentially_matching_orders[matching_indexes[1]].select_for_update()  # buy index
            assert sell_order.get_pair_ids() == buy_order.get_pair_ids()
            assert sell_order.price <= buy_order.price

            make_trade(sell_order, buy_order, trade_at)

        if sell_order.status == ExchangeOrderStatus.FILLED.value:  # type: ignore
            sell_order.advisory_unlock()
            unlocked_orders.add(sell_order.id)
            matching_indexes[0] += 1  # increment sell index
        if buy_order.status == ExchangeOrderStatus.FILLED.value:  # type: ignore
            buy_order.advisory_unlock()
            unlocked_orders.add(buy_order.id)
            matching_indexes[1] -= 1  # increment buy index

        matching_indexes = find_matching_orders(matching_indexes[0], matching_indexes[1], potentially_matching_orders)
        if settings.ONE_TRADE_PER_ITERATION:  # aka one trade per commit
            # Multiple trades per operation lead to a better performance
            # (because of just one complex query per ), but it comes with a trade-off of all trades and
            # corresponding changes are stamped with the same `trade_at` timestamp
            break

    return bool(matching_indexes), unlocked_orders


@log(logger_=logger, level=logging.DEBUG)
def run_single_iteration():
    with transaction.atomic():
        lock = OrderProcessingLock.objects.select_for_update().get()
        # We named it `trade_at`, not `traded_at`, because by the moment we set it the trade is not yet done
        lock.trade_at = trade_at = timezone.now()
        lock.save()

    if not (potentially_matching_orders := get_potentially_matching_orders()):
        return False

    unlocked_order_ids = set()
    try:
        has_more_matches, unlocked_order_ids = match_orders(potentially_matching_orders, trade_at)
    finally:
        assert isinstance(potentially_matching_orders, list)
        ExchangeOrder.objects.advisory_unlock_by_pks({order.id for order in potentially_matching_orders} -
                                                     unlocked_order_ids, ORDER_PROCESSING_LOCK_ID)

    return has_more_matches


def make_lock_metadata():
    hostname = socket.gethostname()
    metadata = {'hostname': hostname, 'pid': os.getpid(), 'argv': sys.argv, 'user': getpass.getuser()}

    # Get Docker container ID (Linux only)
    try:
        with open('/proc/self/cgroup', 'r') as fo:
            for line in fo:
                if 'docker' not in line:
                    continue
                metadata['docker_container_id'] = line.strip().split('/')[-1]
                break
    except Exception:
        pass

    return metadata


@contextmanager
def order_processing_lock(force=False):
    assert not transaction.get_connection().in_atomic_block
    with transaction.atomic():
        lock = OrderProcessingLock.objects.select_for_update().get_or_none()
        if lock and not force and lock.acquired_at:
            raise ThenewbostonRuntimeError(
                f'Order processing lock is already acquired at {lock.acquired_at.isoformat()} '
                f'(extra: {lock.extra})'
            )

        now = timezone.now()
        if lock:
            lock.acquired_at = now
            lock.save()
        else:
            try:
                OrderProcessingLock.objects.create(acquired_at=now, extra=make_lock_metadata())
            except IntegrityError:
                raise ThenewbostonRuntimeError('Order processing lock is already acquired')

    logger.debug('Order processing lock acquired')
    try:
        yield
    finally:
        assert not transaction.get_connection().in_atomic_block
        with transaction.atomic():
            # We do not just delete the lock, because we also store `trade_at` there which is needed for
            # adjusting timestamps of the orders (even when trade processing is not running we should account for
            # those rare cases of adjusting timestamps of the orders)
            # TODO(dmu) LOW: Is `.select_for_update()` necessary here?
            if lock := OrderProcessingLock.objects.select_for_update().get_or_none():
                # TODO(dmu) LOW: We use `acquired_at` as `is_active` flag, but maybe we should have the flag,
                #                so we can use `acquired_at` for debugging purposes?
                lock.acquired_at = None
                lock.save()

        logger.debug('Order processing lock released')


class OrderProcessingEngine:

    def __init__(self, hook_signals=True):
        self.is_running = False

        if hook_signals:
            signal.signal(signal.SIGTERM, lambda sig, _: self.graceful_shutdown())
            signal.signal(signal.SIGINT, lambda sig, _: self.git_int_shutdown())

    def git_int_shutdown(self):
        signal.signal(signal.SIGINT, signal.default_int_handler)
        print('\nHit Ctrl+C again to force shutdown')
        self.graceful_shutdown()

    def graceful_shutdown(self):
        if not self.is_running:
            return

        logger.info('Graceful shutdown initiated')
        self.is_running = False

    def _run_impl(self):
        logger.info('Order processing engine started')

        pubsub = get_redis_client().pubsub()
        pubsub.subscribe(settings.ORDER_PROCESSING_CHANNEL_NAME)

        if (timeout_seconds := settings.ORDER_PROCESSING_CHANNEL_GET_MESSAGE_TIMEOUT_SECONDS) == 0:
            raise ImproperlyConfigured('ORDER_PROCESSING_CHANNEL_GET_MESSAGE_TIMEOUT cannot be 0')

        get_message_iteration_timeout_seconds = min(timeout_seconds, GET_MESSAGE_ITERATION_TIMEOUT_SECONDS)
        try:
            self.is_running = True
            while True:
                timeout_time = time.monotonic() + timeout_seconds
                while self.is_running and time.monotonic() < timeout_time:
                    if message := pubsub.get_message(timeout=get_message_iteration_timeout_seconds):
                        break
                else:
                    message = None

                if not self.is_running:
                    break

                if message is None or (message.get('type') == 'message' and message.get('data') == NEW_ORDER_EVENT):
                    try:
                        while run_single_iteration():  # We run iteration in case of timeout or new order message
                            pass  # We run iterations until we run out of matching orders
                    except Exception:
                        logger.warning('Iteration failed', exc_info=True)
        finally:
            pubsub.unsubscribe()
            pubsub.close()

        logger.info('Order matching engine gracefully stopped')

    def run(self, force=False):
        with order_processing_lock(force=force):
            self._run_impl()
