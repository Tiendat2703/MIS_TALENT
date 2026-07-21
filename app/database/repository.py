import logging
import os
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator

from dotenv import load_dotenv
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

_APP_DIR = Path(__file__).resolve().parents[1]
_WORKSPACE_DIR = _APP_DIR.parent
load_dotenv(_APP_DIR / ".env", override=False)
load_dotenv(_WORKSPACE_DIR / ".env", override=False)

logger = logging.getLogger(__name__)

_db_pool = None
_pool_lock = Lock()


def _pool_limits() -> tuple[int, int]:
    try:
        minconn = int(os.getenv("DB_POOL_MIN", "1"))
        maxconn = int(os.getenv("DB_POOL_MAX", "20"))
    except ValueError as exc:
        raise RuntimeError("DB_POOL_MIN and DB_POOL_MAX must be integers") from exc

    if minconn <= 0 or maxconn <= 0:
        raise RuntimeError("DB pool sizes must be greater than zero")
    if minconn > maxconn:
        raise RuntimeError("DB_POOL_MIN cannot be greater than DB_POOL_MAX")
    return minconn, maxconn


def init_db_pool():
    global _db_pool

    if _db_pool is not None:
        return _db_pool

    with _pool_lock:
        if _db_pool is not None:
            return _db_pool

        password = os.getenv("SUPABASE_PASSWORD") or os.getenv("SUPABASE_DB_PASSWORD")

        if not password:
            raise RuntimeError("Missing SUPABASE_PASSWORD")

        minconn, maxconn = _pool_limits()
        _db_pool = pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            user=os.getenv("SUPABASE_DB_USER") or os.getenv("user", "postgres"),
            password=password,
            host=os.getenv("SUPABASE_DB_HOST", "aws-0-ap-southeast-1.pooler.supabase.com"),
            port=os.getenv("SUPABASE_DB_PORT", "6543"),
            database=os.getenv("SUPABASE_DB_NAME") or os.getenv("database", "postgres"),
            sslmode="require",
            connect_timeout=int(os.getenv("SUPABASE_CONNECT_TIMEOUT", "15")),
        )
        logger.info(
            "Database pool initialized (minconn=%d, maxconn=%d)",
            minconn,
            maxconn,
        )
    return _db_pool


def query_db(query: str, params=None):
    db_pool = init_db_pool()
    connection = db_pool.getconn()

    try:
        with connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(query, params)

            if cursor.description is not None:
                result = [dict(row) for row in cursor.fetchall()]
            else:
                result = None

        connection.commit()
        return result

    except Exception as exc:
        connection.rollback()
        # Do not emit SQL parameters or connection details into application logs.
        logger.error("Database query failed (%s)", type(exc).__name__)
        raise

    finally:
        db_pool.putconn(connection)


@contextmanager
def transaction_cursor() -> Iterator[RealDictCursor]:
    """Yield one cursor bound to one short explicit database transaction."""
    db_pool = init_db_pool()
    connection = db_pool.getconn()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
        connection.commit()
    except Exception as exc:
        connection.rollback()
        logger.error("Database transaction failed (%s)", type(exc).__name__)
        raise
    finally:
        db_pool.putconn(connection)


def close_db_pool() -> None:
    """Close all pooled database connections owned by this process."""
    global _db_pool

    if _db_pool is None:
        return

    _db_pool.closeall()
    _db_pool = None
    logger.info("Database pool closed")


if __name__ == "__main__":
    products = query_db("SELECT * FROM bank_product")
    print(products)
