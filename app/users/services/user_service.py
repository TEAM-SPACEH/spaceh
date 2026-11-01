"""M-02 내 정보 조회·수정 서비스.

메소드: get_user_info, verify_current_password, validate_password, change_password.
비밀번호 해시·검증은 core/security.py, DB 접근은 repository(user_repository)를 쓴다.
(계층 규칙: views → services → repositories. 서비스는 SQL을 직접 부르지 않는다.)
"""

import logging
import string

from app.auth.session import get_current_user_id
from app.users.repositories import user_repository
from core.security import hash_password, verify_password

logger = logging.getLogger(__name__)

# 새 비밀번호 규칙 (validate_password에서 쓴다). 팀 정책이 정해지면 이 값만 바꾼다.
_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 20


def get_user_info(user_id: int) -> dict | None:
    """M-02 로그인 사용자의 이름·사원번호·역할·소속 기업을 조회한다. 없으면 None.

    본인 정보만 볼 수 있다. 요청한 user_id가 현재 로그인한 사용자와 다르면 None을 돌려준다.
    (users 테이블에 email 컬럼이 아직 없어 email은 None으로 돌려준다. 스키마 추가 시 채운다.)
    """
    # 본인 정보만 조회하도록 제한한다. 남의 user_id를 넘겨도 열어 주지 않는다.
    if user_id != get_current_user_id():
        logger.info("내 정보 조회 거부: 본인이 아닌 user_id 요청")
        return None

    row = user_repository.find_profile_by_id(user_id)
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
    stored_hash = user_repository.find_password_hash_by_id(user_id)
    if stored_hash is None:
        return False
    # 평문끼리 비교하지 않고, 저장된 해시와 대조한다 (core/security.py).
    return verify_password(current_password, stored_hash)


def validate_password(password: str) -> bool:
    """M-02 새 비밀번호가 길이·형식 조건을 만족하는지 검증한다.

    조건: 8~20자, 공백 없음, 영문자와 숫자를 각각 1개 이상 포함.
    """
    if not password:
        return False
    if not (_MIN_PASSWORD_LENGTH <= len(password) <= _MAX_PASSWORD_LENGTH):
        return False
    if any(ch.isspace() for ch in password):  # 공백 포함 금지
        return False
    # isalpha()·isdigit()는 한글·유니코드 숫자(²)도 참이라, ASCII 영문자·숫자로만 센다.
    has_letter = any(ch in string.ascii_letters for ch in password)
    has_digit = any(ch in string.digits for ch in password)
    return has_letter and has_digit


def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    """M-02 현재 비밀번호를 확인하고 새 비밀번호를 검증한 뒤 DB의 비밀번호 해시를 바꾼다.

    본인 계정만 바꿀 수 있다(get_user_info와 같은 규칙). 현재 비밀번호가 틀리거나
    새 비밀번호가 규칙에 안 맞으면 바꾸지 않고 False를 돌려준다.
    """
    # 0) 본인만 변경할 수 있다.
    if user_id != get_current_user_id():
        logger.info("비밀번호 변경 거부: 본인이 아닌 user_id 요청")
        return False
    # 1) 현재 비밀번호 확인
    if not verify_current_password(user_id, current_password):
        logger.info("비밀번호 변경 실패: 현재 비밀번호 불일치")
        return False
    # 2) 새 비밀번호 형식 검증
    if not validate_password(new_password):
        logger.info("비밀번호 변경 실패: 새 비밀번호 형식 불만족")
        return False

    # 3) 새 비밀번호를 해시해서 저장한다 (평문 저장 금지).
    updated = user_repository.update_password(user_id, hash_password(new_password))
    if updated == 0:  # 그 사이 계정이 사라진 경우 등
        logger.warning("비밀번호 변경 실패: 사용자를 찾지 못함")
        return False
    logger.info("비밀번호 변경 성공")
    return True
