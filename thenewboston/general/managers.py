from django.db.models import BooleanField, Func, Manager, NullBooleanField, QuerySet
from django.db.models.expressions import RawSQL


def make_advisory_lock_expression(lock_id: int):
    return RawSQL('(id # (%s::bigint << %s))', (lock_id, 64 - lock_id.bit_length()))


class PgAdvisoryLock(Func):
    function = 'pg_advisory_lock'
    output_field = NullBooleanField()


class PgAdvisoryXactLock(Func):
    function = 'pg_advisory_xact_lock'
    output_field = NullBooleanField()


class PgAdvisoryUnlock(Func):
    function = 'pg_advisory_unlock'
    output_field = BooleanField()


class CustomQuerySet(QuerySet):

    def get_or_none(self, *args, **kwargs):
        try:
            return self.get(*args, **kwargs)
        except self.model.DoesNotExist:
            pass

    def with_advisory_lock(self, lock_id: int):
        return self.annotate(advisory_lock=PgAdvisoryLock(make_advisory_lock_expression(lock_id)))

    def with_advisory_xact_lock(self, lock_id: int):
        return self.annotate(advisory_lock=PgAdvisoryXactLock(make_advisory_lock_expression(lock_id)))

    def with_advisory_unlock(self, lock_id: int):
        return self.annotate(advisory_lock=PgAdvisoryUnlock(make_advisory_lock_expression(lock_id)))


class CustomManager(Manager.from_queryset(CustomQuerySet)):  # type: ignore

    def advisory_unlock_by_pks(self, pks, lock_id: int):
        for _ in self.filter(pk__in=pks).with_advisory_unlock(lock_id).values_list('advisory_unlock', flat=True):
            pass
