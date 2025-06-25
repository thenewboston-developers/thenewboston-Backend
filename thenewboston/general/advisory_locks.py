from django.db import connection
from django.db.models import BooleanField, Func, NullBooleanField
from django.db.models.expressions import RawSQL


class PgAdvisoryLock(Func):
    function = 'pg_advisory_lock'
    output_field = NullBooleanField()


class PgTryAdvisoryLock(Func):
    function = 'pg_try_advisory_lock'
    output_field = NullBooleanField()


class PgAdvisoryXactLock(Func):
    function = 'pg_advisory_xact_lock'
    output_field = NullBooleanField()


class PgAdvisoryUnlock(Func):
    function = 'pg_advisory_unlock'
    output_field = BooleanField()


def clear_all_advisory_locks():
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_unlock_all()')


def make_advisory_lock_expression(lock_id: int, row_id='id') -> str:
    return f'({row_id} # ({lock_id}::bigint << {64 - lock_id.bit_length()}))'


def make_advisory_lock_expression_raw_sql(lock_id: int, row_id='id') -> RawSQL:
    return RawSQL(make_advisory_lock_expression(lock_id, row_id=row_id), ())
