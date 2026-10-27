"""M-01 로그인 서비스: login(), logout().

사전에 등록된 사원번호·비밀번호가 users 테이블의 값과 일치하는지 확인해 로그인한다.
비밀번호 해시·검증은 core/security.py, 사용자 조회는 repository(users 테이블),
세션 저장은 session.py가 맡는다. 이 서비스는 st.*·SQL을 직접 부르지 않는다.
"""

import logging

from app.auth import session
from app.auth.repositories import user_repository
from core.security import verify_password

logger = logging.getLogger(__name__)


def login(employee_no: str, password: str) -> bool:
    """M-01 사원번호·비밀번호가 맞고 활성 계정이면 세션에 로그인하고 True를 돌려준다."""
    employee_no = (employee_no or "").strip()
    if not employee_no or not password:
        return False

    user = user_repository.find_user_by_employee_no(employee_no)
    if user is None:
        logger.info("로그인 실패: 등록되지 않은 사원번호")
        return False
    if not user["is_active"]:
        logger.info("로그인 실패: 비활성 계정")
        return False
    if not verify_password(password, user["password_hash"]):
        logger.info("로그인 실패: 비밀번호 불일치")
        return False

    # 세션에는 비밀번호 해시를 빼고, S-03 권한 필터가 쓸 역할·소속까지 넣는다.
    session.set_current_user(
        {
            "id": user["id"],
            "employee_no": user["employee_no"],
            "name": user["name"],
            "role": user["role"],
            "company_id": user["company_id"],
        }
    )
    logger.info("로그인 성공")
    return True


def logout() -> None:
    """M-01 현재 로그인 상태를 해제한다."""
    session.clear_current_user()
