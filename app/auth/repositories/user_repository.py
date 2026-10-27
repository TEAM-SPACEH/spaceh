"""M-01 사용자 저장소. users 테이블을 읽는다 (SQL 값은 %s 바인딩만 쓴다)."""

from core.database import get_connection


def find_user_by_employee_no(employee_no: str) -> dict | None:
    """M-01 사원번호로 사용자 한 명을 조회한다. 없으면 None (DictCursor 행)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, employee_no, password_hash, name, role, company_id, is_active "
            "FROM users WHERE employee_no = %s",
            (employee_no,),
        )
        return cur.fetchone()
