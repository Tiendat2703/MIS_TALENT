import logging
import os

from dotenv import load_dotenv
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

load_dotenv()

logger = logging.getLogger(__name__)

_db_pool = None


def init_db_pool():
    global _db_pool

    if _db_pool is None:
        password = os.getenv("SUPABASE_PASSWORD")

        if not password:
            raise RuntimeError("Missing SUPABASE_PASSWORD")

        _db_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            user=os.getenv("user", "postgres"),
            password=os.getenv("SUPABASE_PASSWORD"),
            host=os.getenv("SUPABASE_DB_HOST", "aws-0-ap-southeast-1.pooler.supabase.com"),
            port=os.getenv("SUPABASE_DB_PORT", "6543"),
            database=os.getenv("SUPABASE_DB_NAME", "postgres"),
            sslmode="require",
            connect_timeout=int(os.getenv("SUPABASE_CONNECT_TIMEOUT", "15")),
        )
        logger.info("Database pool initialized")


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
