import getpass
import logging
import os
import signal
import socket
import sys
import time
from contextlib import contextmanager
from itertools import chain

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.db.models import Case, ExpressionWrapper, F, FloatField, IntegerField, Max, Min, Q, When, Window
from django.utils import timezone

from thenewboston.general.clients.redis import get_redis_client
from thenewboston.general.exceptions import ThenewbostonRuntimeError
from thenewboston.general.misc import ExtractEpoch
from thenewboston.general.utils.logging import log
from thenewboston.general.utils.pytest import is_pytest_running
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
    # TODO(dmu) CRITICAL: Original implementation always generated `deposit_account_number` and `deposit_signing_key`,
    #                     but with `.get_or_create()` reuse there a conditional related to `internal` and `external`
    #                     currencies. Is it an overlook in the original implementation or intentional? Fix or just
    #                     remove this comment.
    wallet, is_created = Wallet.objects.get_or_create(
        owner=owner, currency=currency, defaults=defaults, _for_update=True
    )
    if not is_created:
        defaults.pop('balance', None)
        for attr, value in defaults.items():
            setattr(wallet, attr, value)

        # We should not adjust timestamps because the wallet update happens within the trade
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

    logger.debug('Trading at %s (quantity: %s): "%s" vs "%s"', trade_price, filled_quantity, buy_order, sell_order)
    # TODO(dmu) MEDIUM: Figure out the best order of saving trade, wallet and orders updates, because it affects
    #                   the order of events being streamed to the clients
    Trade.objects.create(
        buy_order=buy_order,
        sell_order=sell_order,
        filled_quantity=filled_quantity,
        price=trade_price,
        overpayment_amount=overpayment_amount,
        created_date=trade_at,
        modified_date=trade_at,
    )

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
def get_potentially_matching_orders(trade_at=None):
    trade_at = trade_at or timezone.now()
    subquery = (
        ExchangeOrder.objects.filter(status__in=UNFILLED_STATUSES, created_date__lte=trade_at).annotate(
            best_sell_price=Window(
                expression=Min('price', filter=Q(side=SELL)),
                partition_by=('primary_currency_id', 'secondary_currency_id'),
            ),
            best_buy_price=Window(
                expression=Max('price', filter=Q(side=BUY)),
                partition_by=('primary_currency_id', 'secondary_currency_id'),
            ),
        ).filter(Q(side=BUY, price__gte=F('best_sell_price')) | Q(side=SELL, price__lte=F('best_buy_price'))).annotate(
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
        ).only('pk')
    )
    return list(
        # We need it to be subquery for two related reasons:
        # 1. We need it to run as single query on the database for consistency and race condition prevention
        # 2. We need it to lock only on potentially matching, not on all orders in the database
        ExchangeOrder.objects.filter(pk__in=subquery).with_advisory_lock(ORDER_PROCESSING_LOCK_ID).annotate(
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
            sort_created_timestamp=Case(
                When(side=SELL, then=ExtractEpoch(F('created_date'))),
                When(side=BUY, then=ExpressionWrapper(-ExtractEpoch(F('created_date')), output_field=FloatField())),
                output_field=FloatField(),
            ),
        ).order_by(
            'side',  # SELL will be first, then BUY
            'sort_primary_currency_id',
            'sort_secondary_currency_id',
            'price',  # lowest ask first (best sell goes first), then highest bid (best buy goes last)
            'sort_created_timestamp',
            'id',  # for stable ordering in case of exactly equal created_date
        )
    )


def find_matching_orders(sell_index, buy_index, potentially_matching_orders: list) -> list[int] | None:
    if len(potentially_matching_orders) < 2:  # defensive guard condition
        return None

    while sell_index is not None and buy_index is not None and sell_index < buy_index:
        logger.debug('Check orders match at indices: sell_index=%s, buy_index=%s', sell_index, buy_index)
        sell_order = potentially_matching_orders[sell_index]
        if sell_order.side == BUY:  # no more sell orders
            logger.debug('Sell orders exhausted at index %s', sell_index)
            break

        buy_order = potentially_matching_orders[buy_index]
        if buy_order.side == SELL:  # no more buy orders
            logger.debug('Buy orders exhausted at index %s', buy_index)
            break

        sell_order_pair = sell_order.get_pair_ids()
        assert isinstance(sell_order_pair[0], int) and isinstance(sell_order_pair[1], int)
        logger.debug('Sell order pair: %s', sell_order_pair)
        buy_order_pair = buy_order.get_pair_ids()
        assert isinstance(buy_order_pair[0], int) and isinstance(buy_order_pair[1], int)
        logger.debug('Buy order pair: %s', buy_order_pair)

        if buy_order_pair < sell_order_pair:  # catch up currency pair for the buy orders
            buy_index = advance_to_next_pair(buy_index, potentially_matching_orders)
            logger.debug('Advanced buy index to %s after currency pair mismatch', buy_index)
            continue
        elif sell_order_pair < buy_order_pair:  # catch up currency pair for the sell orders
            # TODO(dmu) MEDIUM: Cover this clause with unittests
            sell_index = advance_to_next_pair(sell_index, potentially_matching_orders)
            logger.debug('Advanced sell index to %s after currency pair mismatch', sell_index)
            continue

        assert sell_order_pair == buy_order_pair
        if sell_order.price > buy_order.price:  # there is no match let's go to another currency pair
            # We probably never get here in production because of how get_potentially_matching_orders() works
            logger.debug('Price mismatch: sell_order.price=%s, buy_order.price=%s', sell_order.price, buy_order.price)
            sell_index = advance_to_next_pair(sell_index, potentially_matching_orders)
            logger.debug('Advanced sell index to %s after price mismatch', sell_index)
            buy_index = advance_to_next_pair(buy_index, potentially_matching_orders)
            logger.debug('Advanced buy index to %s after price mismatch', sell_index)
            continue

        logger.debug('Found matching orders: sell_index=%s, buy_index=%s', sell_index, buy_index)
        return [sell_index, buy_index]  # we found a pair of orders that can be matched

    logger.debug('No matching orders found')
    return None


def match_orders(potentially_matching_orders, trade_at) -> tuple[bool, set[int]]:
    potentially_matching_orders_len = len(potentially_matching_orders)
    if potentially_matching_orders_len < 2:  # defensive guard condition
        return False, set()

    unlocked_orders = set()
    matching_indexes = find_matching_orders(0, potentially_matching_orders_len - 1, potentially_matching_orders)

    # We use for-loop instead of `while matching_indexes:` to prevent infinite loop in case of implementation bugs
    # (defensive programming)
    for _ in range(potentially_matching_orders_len):
        if not matching_indexes:
            break

        original_matching_indexes = matching_indexes.copy()
        assert len(matching_indexes) == 2

        # This is important that we are not in transaction, so every trade results into saving data to the database
        # and streaming events to the clients (because it is done on commit)
        assert not transaction.get_connection().in_atomic_block or is_pytest_running()
        with transaction.atomic():
            # We use advisory locks when getting potentially matching orders instead of regular database locks
            # to be able to commit after each trade therefore stream events trade by trade and allow updated
            # order statuses and wallet balances earlier (before completing the entire match).
            #
            # Race condition prevention mechanisms in use:
            # - Potentially matching orders are fetched with session scoped advisory locks.
            # - On API level we require transaction scoped advisory locks and regular row level database locks
            #   (`.select_for_update()`) for update operations (therefore any updates are delayed).
            # - On model level we prohibit updates of order attributes other than 'status', 'filled_quantity',
            #   'modified_date'.
            # - Orders are selected with regular row level database locks (`.select_for_update()`) rights
            #   before the trade is made
            #
            # The above measures may still leak changes to the order via Django Admin or direct database access
            # between getting potentially matching orders and making a trade. We assume that if someone is making
            # changes directly to the database they know what they are doing and can handle the consequences therefore
            # we will make extra checks against Django Admin changes.
            sell_order = potentially_matching_orders[matching_indexes[0]].select_for_update()  # sell index
            buy_order = potentially_matching_orders[matching_indexes[1]].select_for_update()  # buy index

            # These are algorithm correctness asserts, not runtime error handling against direct database access
            # (although they serve as an extra preventive measure in case asserts are not disable in production)
            assert sell_order.get_pair_ids() == buy_order.get_pair_ids()
            assert sell_order.price <= buy_order.price

            # Because it allowed to change only status and filled_quantity for order (in Django Admin)
            # they are still matching by price, so we check for status change and advance to the next order
            if sell_order.status not in UNFILLED_STATUSES or sell_order.unfilled_quantity <= 0:
                matching_indexes[0] += 1  # increment sell index
            elif buy_order.status not in UNFILLED_STATUSES or buy_order.unfilled_quantity <= 0:
                matching_indexes[1] += 1  # increment buy index
            else:
                make_trade(sell_order, buy_order, trade_at)
                if sell_order.status == ExchangeOrderStatus.FILLED.value:  # type: ignore
                    matching_indexes[0] += 1  # increment sell index
                if buy_order.status == ExchangeOrderStatus.FILLED.value:  # type: ignore
                    matching_indexes[1] -= 1  # increment buy index

        matching_indexes = find_matching_orders(matching_indexes[0], matching_indexes[1], potentially_matching_orders)

        # Remove advisory locks for the orders that were have already processed
        if matching_indexes:
            logger.debug('Producing generator index gap')
            index_generator = chain(
                (index for index in range(original_matching_indexes[0], matching_indexes[0], 1)),
                (index for index in range(original_matching_indexes[1], matching_indexes[1], -1)),
            )
        else:
            logger.debug('Producing generator for unmet indexes')
            assert original_matching_indexes[0] < original_matching_indexes[1]
            index_generator = range(original_matching_indexes[0], original_matching_indexes[1] + 1)  # type: ignore

        for order_index in index_generator:
            logger.debug('Unlocking order at index %s: %s', order_index, potentially_matching_orders[order_index])
            order = potentially_matching_orders[order_index]
            order.advisory_unlock(ORDER_PROCESSING_LOCK_ID)
            unlocked_orders.add(order.id)

        if settings.ONE_TRADE_PER_ITERATION:  # aka one trade per commit
            # Multiple trades per operation lead to a better performance
            # (because of just one complex query per ), but it comes with a trade-off of all trades and
            # corresponding changes are stamped with the same `trade_at` timestamp
            break

    return bool(matching_indexes), unlocked_orders


@log(logger_=logger, level=logging.DEBUG)
def run_single_iteration():
    with transaction.atomic():
        # We use `.get()` here because
        # 1) There must be OrderProcessingLock instance created by now with:
        #    `thenewboston.exchange.order_processing.engine.order_processing_lock`
        # 2) There can be only one instance of OrderProcessingLock
        lock = OrderProcessingLock.objects.select_for_update().get()
        # We named it `trade_at`, not `traded_at`, because by the moment we set it the trade is not yet done
        lock.trade_at = trade_at = timezone.now()
        lock.save()

    unlocked_order_ids = set()
    potentially_matching_orders = []  # putting a dummy value, so get_potentially_matching_orders() moved into `try`
    try:
        if not (potentially_matching_orders := get_potentially_matching_orders(trade_at)):
            return False
        has_more_matches, unlocked_order_ids = match_orders(potentially_matching_orders, trade_at)
    finally:
        assert isinstance(potentially_matching_orders, list)
        # Advisory locks are automatically released on database connection close, but as long as we are running
        # we need to maintain the cleanup
        ExchangeOrder.objects.advisory_unlock_by_pks({order.id for order in potentially_matching_orders} -
                                                     unlocked_order_ids, ORDER_PROCESSING_LOCK_ID)

    # `has_more_matches` may be True for `settings.ONE_TRADE_PER_ITERATION = True`. It is used in the outer loop
    # to continue processing orders until there are no more matches
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
    assert not transaction.get_connection().in_atomic_block or is_pytest_running()
    with transaction.atomic():
        lock = OrderProcessingLock.objects.select_for_update().get_or_none()
        if lock and not force and lock.acquired_at:
            raise ThenewbostonRuntimeError(
                f'Order processing lock is already acquired at {lock.acquired_at.isoformat()} '
                f'(extra: {lock.extra})'
            )

        now = timezone.now()
        if lock:  # case of existing lock record which is not acquired, or force
            lock.acquired_at = now
            lock.save()
        else:
            try:
                OrderProcessingLock.objects.create(acquired_at=now, extra=make_lock_metadata())
            except IntegrityError:
                # This handles race condition when another process manager to create the lock before after we
                # initially did not find it in the database
                raise ThenewbostonRuntimeError('Order processing lock is already acquired')

    logger.debug('Order processing lock acquired')
    try:
        yield
    finally:
        assert not transaction.get_connection().in_atomic_block or is_pytest_running()
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
            signal.signal(signal.SIGTERM, lambda sig, _: self.graceful_shutdown())  # Docker stop
            signal.signal(signal.SIGINT, lambda sig, _: self.git_int_shutdown())  # Ctrl + C

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
                    # We need to wake up periodically to check if we should exit
                    if message := pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=get_message_iteration_timeout_seconds
                    ):
                        break
                else:
                    message = None

                if not self.is_running:
                    break

                if message is None or (message.get('type') == 'message' and message.get('data') == NEW_ORDER_EVENT):
                    # We did not get a message (maybe there is something wrong with Redis Pub/Sub) or we got
                    # a new order event, so we run the iteration
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
