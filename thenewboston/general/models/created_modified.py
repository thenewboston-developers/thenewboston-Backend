import logging
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone

from .custom_model import CustomModel, TrackerMixin

logger = logging.getLogger(__name__)

MIN_TIME_INCREMENT = timedelta(microseconds=1)


class CreatedModified(CustomModel):
    # TODO(dmu) MEDIUM: Rename `created_date` -> `created_at` and `modified_date` -> `updated_at`
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AdjustableTimestampsModel(TrackerMixin, CustomModel):

    # We are not using `CreatedModified` and defining our own fields here to be able to adjust the timestamps
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True

    def _adjust_timestamps(self, was_adding, had_changes):
        # We adjust timestamps to be after trade started, so any trade that started captures all orders up to
        # the moment of trade start wih regard to logical chronology. While physically the order may have been
        # created (entered to the API) earlier it will still get the timestamp of the trade start + 1 miscrosecond.
        # These guarantees that avery order that should be processed by the trade is actually processed by it.
        # While those were not accessible due technical reasons like database transaction isolation, API processing
        # time, etc while a later creation timestamp and therefore are not eligible for the running trade.

        from thenewboston.exchange.models import OrderProcessingLock

        assert transaction.get_connection().in_atomic_block
        # We do not update lock here, but select for update to make sure we are not in the middle of the update
        if not (lock := OrderProcessingLock.objects.select_for_update().get_or_none()):
            # there is nowhere we can get trade_at from (this may happen in tests or before the very first ran of
            # matching engine)
            return

        if not (trade_at := lock.trade_at):  # in case trade has not started
            return

        adjusted_moment = trade_at + MIN_TIME_INCREMENT
        # In most cases we will not make changes to timestamps, because orders probably come after trade has started
        if was_adding and self.created_date < adjusted_moment:
            self.created_date = adjusted_moment
            # It is not really a warning, but we use it to track what happens in real world
            logger.warning('Adjusting created_date from %s to %s for %s', self.created_date, adjusted_moment, self)

        if (was_adding or had_changes) and self.modified_date < adjusted_moment:
            self.modified_date = adjusted_moment
            # It is not really a warning, but we use it to track what happens in real world
            logger.warning('Adjusting modified_date from %s to %s for %s', self.modified_date, adjusted_moment, self)

    def save(self, *args, should_adjust_timestamps=True, **kwargs):
        if self.has_changes() and not self.has_changed('modified_date'):  # allow explicit modified_date
            self.modified_date = timezone.now()

        if should_adjust_timestamps:
            self._adjust_timestamps(self.is_adding(), self.has_changes())

        return super().save(*args, **kwargs)
