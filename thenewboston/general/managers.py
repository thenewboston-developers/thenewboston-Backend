import logging

from django.db.models import Manager, QuerySet

from thenewboston.general.advisory_locks import (
    PgAdvisoryLock, PgAdvisoryUnlock, PgAdvisoryXactLock, PgTryAdvisoryLock, make_advisory_lock_expression_raw_sql
)

logger = logging.getLogger(__name__)


class CustomQuerySet(QuerySet):

    def get_or_none(self, *args, **kwargs):
        try:
            return self.get(*args, **kwargs)
        except self.model.DoesNotExist:
            pass

    def with_advisory_lock(self, lock_id: int, just_try: bool = False):
        func = PgTryAdvisoryLock if just_try else PgAdvisoryLock
        return self.annotate(advisory_lock=func(make_advisory_lock_expression_raw_sql(lock_id)))

    def with_advisory_xact_lock(self, lock_id: int):
        return self.annotate(advisory_lock=PgAdvisoryXactLock(make_advisory_lock_expression_raw_sql(lock_id)))

    def with_advisory_unlock(self, lock_id: int):
        return self.annotate(advisory_unlock=PgAdvisoryUnlock(make_advisory_lock_expression_raw_sql(lock_id)))


class CustomManager(Manager.from_queryset(CustomQuerySet)):  # type: ignore

    def advisory_unlock_by_pks(self, pks, lock_id: int):
        logger.debug('Unlocking advisory lock %s for pks: %s', lock_id, pks)
        for _ in self.filter(pk__in=pks).with_advisory_unlock(lock_id):
            pass
