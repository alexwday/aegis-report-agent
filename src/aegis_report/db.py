from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row


@contextmanager
def connect(dsn: str, *, source: bool = False) -> Iterator[psycopg.Connection[DictRow]]:
    options = "-c statement_timeout=5000 -c lock_timeout=2000 -c search_path=pg_catalog"
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5, options=options) as conn:
        if source:
            conn.read_only = True
            conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        yield conn
