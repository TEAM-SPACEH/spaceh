"""공통 DB 연결. 모든 repositories는 get_connection()으로만 MySQL에 접속한다."""

from collections.abc import Iterator
from contextlib import contextmanager

import pymysql
from pymysql.connections import Connection

from core import config


@contextmanager
def get_connection() -> Iterator[Connection]:
    """with 블록이 끝나면 commit, 예외가 나면 rollback 후 연결을 닫는다."""
    conn = pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
