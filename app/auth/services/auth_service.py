"""M-01 로그인 서비스: login(), logout().

사전에 등록된 사원번호·비밀번호가 users 테이블의 값과 일치하는지 확인해 로그인한다.
비밀번호 해시·검증은 core/security.py, 사용자 조회는 repository(users 테이블),
세션 저장은 session.py가 맡는다. 이 서비스는 st.*·SQL을 직접 부르지 않는다.
"""

import logging
import re
import threading

from app.admin.services.audit_service import record_audit_log
from app.auth import session
from app.auth.repositories import user_repository
from core.security import verify_password

logger = logging.getLogger(__name__)

# 사원번호 형식: 영문·숫자·하이픈 1~20자 (예: MVX-0001). 이 형식일 때만 감사 로그에 남긴다.
_EMPLOYEE_NO_PATTERN = re.compile(r"[A-Za-z0-9\-]{1,20}")

# 감사 로그 기록을 기다리는 최대 시간(초). DB가 응답하지 않아도 로그인이 이 시간 넘게 멈추지 않게 한다.
_AUDIT_TIMEOUT_SECONDS = 2.0


def _audit_login(user_id: int | None, employee_no: str | None, blocked: bool, reason: str | None) -> None:
    """A-04 로그인 시도(성공·실패)를 감사 로그에 남긴다.

    감사 로그 INSERT는 동기 호출이라, DB가 응답하지 않으면 로그인이 함께 멈출 수 있다
    (core/database.py에 읽기·쓰기 제한 시간이 없고 PyMySQL 기본값도 None이라 예외로도 안 풀린다).
    그래서 기록은 별도 스레드에서 하고 최대 _AUDIT_TIMEOUT_SECONDS만 기다린다. 제한 시간 안에
    못 끝내거나 예외가 나도 로그인은 계속 진행한다(기록 실패가 로그인을 막지 않는다).
    """

    def _write() -> None:
        try:
            record_audit_log(user_id, "login", None, None, blocked, reason, employee_no=employee_no)
        except Exception:
            logger.exception("감사 로그 기록 실패(login)")

    # daemon 스레드라, 기록이 끝내 걸려 있어도 프로그램 종료를 막지 않는다.
    worker = threading.Thread(target=_write, daemon=True)
    worker.start()
    worker.join(_AUDIT_TIMEOUT_SECONDS)
    if worker.is_alive():
        # 제한 시간 안에 못 끝냄(DB 지연 등). 기록은 포기하고 로그인은 계속 진행한다.
        logger.warning("감사 로그 기록 지연으로 건너뜀(login)")


def login(employee_no: str, password: str) -> bool:
    """M-01 사원번호·비밀번호가 맞고 활성 계정이면 세션에 로그인하고 True를 돌려준다.

    로그인 성공과 세 가지 실패(없는 사원번호·비활성 계정·비밀번호 불일치)는 A-04 감사 로그에 남긴다.
    """
    employee_no = (employee_no or "").strip()
    if not employee_no or not password:
        return False

    user = user_repository.find_user_by_employee_no(employee_no)
    if user is None:
        # 사원번호 칸에 비밀번호를 잘못 넣었을 수도 있으니, 형식이 맞는 값만 로그에 남긴다.
        # (감사 로그는 관리자만 보지만, 형식 안 맞는 입력은 비밀번호일 수 있어 아예 남기지 않는다.)
        safe_employee_no = employee_no if _EMPLOYEE_NO_PATTERN.fullmatch(employee_no) else None
        _audit_login(None, safe_employee_no, True, "등록되지 않은 사원번호")
        logger.info("로그인 실패: 등록되지 않은 사원번호")
        return False
    if not user["is_active"]:
        # 여기서부터는 사용자가 확인됐으므로 user_id로 남기고, 입력값(employee_no)은 남기지 않는다.
        _audit_login(user["id"], None, True, "비활성 계정")
        logger.info("로그인 실패: 비활성 계정")
        return False
    if not verify_password(password, user["password_hash"]):
        _audit_login(user["id"], None, True, "비밀번호 불일치")
        logger.info("로그인 실패: 비밀번호 불일치")
        return False

    # 세션에는 비밀번호 해시를 빼고, S-03 권한 필터가 쓸 역할·소속까지 넣는다.
    # 회사 이름은 공통 헤더·사이드바가 "현대무벡스 관리자"처럼 보여 줄 때 쓴다.
    session.set_current_user(
        {
            "id": user["id"],
            "employee_no": user["employee_no"],
            "name": user["name"],
            "role": user["role"],
            "company_id": user["company_id"],
            "company_name": user.get("company_name"),
        }
    )
    _audit_login(user["id"], None, False, None)  # 성공 기록 (세션 저장 다음)
    logger.info("로그인 성공")
    return True


def logout() -> None:
    """M-01 현재 로그인 상태를 해제한다."""
    session.clear_current_user()
