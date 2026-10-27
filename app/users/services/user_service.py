"""M-02 내 정보 조회·수정 서비스.

메소드: get_user_info, verify_current_password, validate_password, change_password.
비밀번호 해시·검증은 core/security.py를, DB 연결은 core/database.py를 쓴다.
(계층 규칙상 SQL은 repositories가 맡지만, 이번 작업이 이 파일로 한정돼 여기에 둔다.)
"""

import logging

from core.database import get_connection
from core.security import hash_password, verify_password

logger = logging.getLogger(__name__)

# 새 비밀번호 규칙 (validate_password에서 쓴다). 팀 정책이 정해지면 이 값만 바꾼다.
_MIN_PASSWORD_LENGTH = 4
_MAX_PASSWORD_LENGTH = 20


def get_user_info(user_id: int) -> dict | None:
    """M-02 로그인 사용자의 이름·사원번호·역할·소속 기업을 조회한다. 없으면 None.

    소속 기업 이름은 companies 테이블과 이어서(LEFT JOIN) 가져온다.
    (users 테이블에 email 컬럼이 아직 없어 email은 None으로 돌려준다. 스키마에 추가되면
     아래 SELECT에 u.email을 넣고 반환 dict의 email을 그 값으로 바꾸면 된다.)
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
        row = cur.fetchone()

    if row is None:
        return None
    return {
        "user_id": row["id"],
        "employee_no": row["employee_no"],
        "name": row["name"],
        "email": None,  # users 테이블에 email 컬럼 없음 (스키마 추가 후 채운다)
        "role": row["role"],
        "company_id": row["company_id"],
        "company_name": row["company_name"],
    }


def verify_current_password(user_id: int, current_password: str) -> bool:
    """M-02 입력한 현재 비밀번호가 DB에 저장된 비밀번호 해시와 일치하는지 확인한다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()

    if row is None:
        return False
    # 평문끼리 비교하지 않고, 저장된 해시와 대조한다 (core/security.py).
    return verify_password(current_password, row["password"])


def validate_password(password: str) -> bool:
    """M-02 새 비밀번호가 길이·형식 조건을 만족하는지 검증한다.

    조건: 4~20자, 공백 없음, 영문자와 숫자를 각각 1개 이상 포함.
    """
    if not password:
        return False
    if not (_MIN_PASSWORD_LENGTH <= len(password) <= _MAX_PASSWORD_LENGTH):
        return False
    if any(ch.isspace() for ch in password):  # 공백 포함 금지
        return False
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_letter and has_digit


def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    """M-02 현재 비밀번호를 확인하고 새 비밀번호를 검증한 뒤 DB의 비밀번호 해시를 바꾼다.

    현재 비밀번호가 틀리거나 새 비밀번호가 규칙에 안 맞으면 바꾸지 않고 False를 돌려준다.
    """
    # 1) 현재 비밀번호 확인
    if not verify_current_password(user_id, current_password):
        logger.info("비밀번호 변경 실패: 현재 비밀번호 불일치")
        return False
    # 2) 새 비밀번호 형식 검증
    if not validate_password(new_password):
        logger.info("비밀번호 변경 실패: 새 비밀번호 형식 불만족")
        return False

    # 3) 새 비밀번호를 해시해서 저장한다 (평문 저장 금지).
    new_hash = hash_password(new_password)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET password = %s WHERE id = %s", (new_hash, user_id))
        updated = cur.rowcount

    if updated == 0:  # 그 사이 계정이 사라진 경우 등
        logger.warning("비밀번호 변경 실패: 사용자를 찾지 못함")
        return False
    logger.info("비밀번호 변경 성공")
    return True
