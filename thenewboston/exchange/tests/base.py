from django.db import connection

from thenewboston.general.advisory_locks import make_advisory_lock_expression

BASE_SQL_QUERY = """
    SELECT 1 FROM pg_locks
    WHERE locktype = 'advisory'
      AND granted
      AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
"""


def exists(raw_sql):
    with connection.cursor() as cursor:
        cursor.execute(raw_sql)
        return bool(cursor.fetchone())


def is_advisory_lock_set(lock_id: int, row_id: int):
    # We have to use function like this because in PostgreSQL there is no way to check if advisory lock has been set
    # acquired in the same session.
    lock_expression = make_advisory_lock_expression(lock_id, row_id=row_id)
    return exists(
        f"""
            {BASE_SQL_QUERY}
              AND classid = ({lock_expression} >> 32)::int
              AND objid = ({lock_expression} & ((1::bigint << 32) - 1))::int
            LIMIT 1
        """
    )


def has_advisory_locks():
    return exists(f'{BASE_SQL_QUERY} LIMIT 1')
