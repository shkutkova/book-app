"""Подключение к базе. Остальной код пишет только fetch_all / fetch_one / transaction."""
import os
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    """Пул открывается при первом запросе: подключение к Supabase — самая медленная часть,
    поэтому соединения переиспользуются, а не создаются на каждую страницу."""
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("Не задана переменная DATABASE_URL в .env")
        _pool = ConnectionPool(
            url, min_size=1, max_size=5, open=True,
            # без подготовленных запросов: иначе ломается пул подключений Supabase
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
        )
    return _pool


def fetch_all(sql: str, params: dict | tuple | None = None) -> list[dict]:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: dict | tuple | None = None) -> dict | None:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchone()


@contextmanager
def transaction():
    """Несколько изменений, которые должны пройти вместе или не пройти вовсе."""
    with pool().connection() as conn, conn.transaction():
        yield conn
