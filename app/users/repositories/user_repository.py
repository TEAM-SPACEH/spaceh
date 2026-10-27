"""M-02 사용자 저장소. users 테이블 읽기/쓰기를 맡는다 (SQL 값은 %s 바인딩만 쓴다)."""

from core.database import get_connection


def find_profile_by_id(user_id: int) -> dict | None:
    """M-02 user_id로 이름·사원번호·역할·소속 기업을 조회한다. 없으면 None.

    소속 기업 이름은 companies 테이블과 이어서(LEFT JOIN) 가져온다.
    (users 테이블에 email 컬럼이 아직 없다. 추가되면 SELECT에 u.email을 넣는다.)
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.employee_no, u.name, u.role,
                   u.company_id, c.name AS company_name
            FROM users u
            LEFT JOIN companies c ON c.company_id = u.company_id
            WHERE u.id = %s
            """,
            (user_id,),
        )
        return cur.fetchone()


def find_password_hash_by_id(user_id: int) -> str | None:
    """M-02 user_id의 비밀번호 해시를 조회한다. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    return row["password"] if row else None


def update_password(user_id: int, password_hash: str) -> int:
    """M-02 user_id의 비밀번호 해시를 바꾸고, 바뀐 행 수를 돌려준다(없으면 0)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET password = %s WHERE id = %s", (password_hash, user_id))
        return cur.rowcount
