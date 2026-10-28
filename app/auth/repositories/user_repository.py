"""M-01 사용자 저장소. users 테이블을 읽는다 (SQL 값은 %s 바인딩만 쓴다)."""

from core.database import get_connection


def find_user_by_employee_no(employee_no: str) -> dict | None:
    """M-01 사원번호로 사용자 한 명과 소속 회사 이름을 조회한다. 없으면 None (DictCursor 행)."""
    # 최종 어드민은 소속(company_id)이 없으므로 LEFT JOIN으로 company_name을 NULL로 받는다.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.employee_no, u.password_hash, u.name, u.role, u.company_id, u.is_active, "
            "c.name AS company_name "
            "FROM users u LEFT JOIN companies c ON c.company_id = u.company_id "
            "WHERE u.employee_no = %s",
            (employee_no,),
        )
        return cur.fetchone()
