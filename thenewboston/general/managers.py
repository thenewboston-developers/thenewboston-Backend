import logging

from django.db import transaction
from django.db.models import Manager, QuerySet
from django.db.models.query import resolve_callables
from django.db.utils import IntegrityError

from thenewboston.general.advisory_locks import (
    PgAdvisoryLock,
    PgAdvisoryUnlock,
    PgAdvisoryXactLock,
    PgTryAdvisoryLock,
    make_advisory_lock_expression_raw_sql,
)

logger = logging.getLogger(__name__)


class CustomQuerySet(QuerySet):
    def get_or_none(self, *args, **kwargs):
        try:
            return self.get(*args, **kwargs)
        except self.model.DoesNotExist:
            pass

    def get_or_create_for_update(self, defaults=None, **kwargs):
        # TODO(dmu) HIGH: Not used anywhere, but decided to keep it. The implementation was not tested
        #                 Delete it if we do not start using it within a month or so.
        assert transaction.get_connection().in_atomic_block

        defaults = defaults or {}
        model = self.model
        try:
            return model.objects.select_for_update().get(**kwargs), False
        except model.DoesNotExist:
            params = self._extract_model_params(defaults, **kwargs)
            try:
                params = dict(resolve_callables(params))
                return model.objects.select_for_update().get(pk=self.create(**params).pk), True
            except IntegrityError:
                try:
                    return model.objects.select_for_update().get(**kwargs), False
                except self.model.DoesNotExist:
                    pass

                raise

    def with_advisory_lock(self, lock_id: int, just_try: bool = False, row_id: str = 'id'):
        func = PgTryAdvisoryLock if just_try else PgAdvisoryLock
        return self.annotate(advisory_lock=func(make_advisory_lock_expression_raw_sql(lock_id, row_id=row_id)))

    def with_advisory_xact_lock(self, lock_id: int):
        return self.annotate(advisory_lock=PgAdvisoryXactLock(make_advisory_lock_expression_raw_sql(lock_id)))

    def with_advisory_unlock(self, lock_id: int):
        return self.annotate(advisory_unlock=PgAdvisoryUnlock(make_advisory_lock_expression_raw_sql(lock_id)))


class CustomManager(Manager.from_queryset(CustomQuerySet)):  # type: ignore
    def advisory_unlock_by_pks(self, pks, lock_id: int):
        logger.debug('Unlocking advisory lock %s for pks: %s', lock_id, pks)
        for _ in self.filter(pk__in=pks).with_advisory_unlock(lock_id):
            pass
