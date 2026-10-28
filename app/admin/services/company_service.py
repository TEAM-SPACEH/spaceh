"""A-07 계열사 등록·조회·수정.

A-07 계열사 동적 추가 = 최종 어드민이 새 회사를 등록하면 필터·권한·보고서 대상에 바로 들어가게 하는 기능이다.
회사는 고정 목록이 아니라 companies 테이블에서 읽는다 (docs/architecture/data-model.md). 다른 화면(검색 필터 등)은
회사 목록을 직접 적지 말고 get_company_options() 를 불러 쓴다.

역할 분담
- 이 파일(services): 최종 어드민 권한 확인, 입력 검증 호출, 중복 오류를 쉬운 문구로 바꾸기, 결과 모양 만들기.
- validators: 입력값 형식 검증 / company_repository: SQL 실행만 한다.

권한 (docs/architecture/overview.md §2.2): 계열사 추가·DART 설정은 최종 어드민만 할 수 있다.

감사 로그 (A-04): 계열사 등록·DART 고유번호 변경은 기록하고, 최종 어드민이 아닌 사용자의 시도는 막힌 것(blocked)으로 기록한다.
"""

import logging

from app.admin import validators
from app.admin.repositories import company_repository
from app.admin.repositories.company_repository import DuplicateCompanyError
from app.admin.services.audit_service import record_audit_log
from core.constants import ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

# audit_logs.action 값. 감사 로그 화면의 행동 이름은 audit_service.ACTION_LABELS 에 있다.
ACTION_COMPANY_CREATE = "company_create"
ACTION_COMPANY_UPDATE = "company_update"

# 겹친 값의 종류별 안내 문구. 사용자가 입력한 값은 문구에 넣지 않는다 (화면에 그대로 보여 줘도 안전하게).
_DUPLICATE_MESSAGES = {
    "company_id": "이미 사용 중인 회사 코드입니다.",
    "name": "이미 등록된 회사명입니다.",
    "dart_code": "이미 다른 계열사에 등록된 DART 고유번호입니다.",
}


def get_companies(user: dict) -> list[dict]:
    """A-07 계열사 목록을 문서·보안 등급 분포·사용자 수와 함께 조회한다.

    user: 로그인 사용자. 최종 어드민만 볼 수 있다
    반환: 계열사 dict 목록. 각 dict: company_id, name, dart_code(없으면 None), is_active(bool),
        default_share_enabled(bool), doc_total, doc_public, doc_internal, doc_confidential, user_count
    PermissionError: 최종 어드민이 아닐 때
    """
    _require_super_admin(user)
    return [_to_company(row) for row in company_repository.list_companies()]


def get_company_options() -> list[dict]:
    """A-07 사용 중인 계열사의 {"id": 코드, "name": 회사명} 목록을 돌려준다 (검색 필터·보고서 대상 선택지용).

    로그인한 누구나 필터 선택지가 필요하므로 권한을 묻지 않는다. 새 계열사를 등록하면 여기에 바로 나온다.
    """
    return company_repository.list_active_company_options()


def create_company(
    user: dict,
    name: str,
    company_id: str,
    dart_code: str = "",
    default_share_enabled: bool = False,
) -> dict:
    """A-07 새 계열사를 등록한다.

    user: 로그인 사용자. 최종 어드민만 할 수 있다
    name: 회사명 (앞뒤 공백 제거, 최대 100자)
    company_id: 회사 코드. 영문 2–5자(소문자는 대문자로 바꿔 받는다). 사원번호 앞부분이라 등록 뒤 바꿀 수 없다
    dart_code: DART 고유번호 숫자 8자리. 상장사만 입력하고, 비우면 입력 전(None)으로 둔다
    default_share_enabled: 새 사내 문서를 올릴 때 그룹사 공유를 켠 채로 시작할지
    반환: {"company_id", "name", "dart_code", "default_share_enabled", "status": "success", "message": ...}
    PermissionError: 최종 어드민이 아닐 때
    ValueError: 형식이 틀렸거나 코드·회사명·DART 고유번호가 이미 있을 때 (화면에 그대로 보여 줄 수 있는 문구)
    """
    # 권한 확인이 입력 검증·DB 접근보다 먼저다. 막힌 시도도 감사 로그에 남긴다.
    _require_super_admin(user, ACTION_COMPANY_CREATE)
    name = validators.validate_company_name(name)
    company_id = validators.validate_company_code(company_id)
    dart_code = validators.validate_dart_code(dart_code)
    share = bool(default_share_enabled)

    try:
        company_repository.insert_company(company_id, name, dart_code, share)
    except DuplicateCompanyError as exc:
        raise ValueError(_DUPLICATE_MESSAGES[exc.kind]) from exc
    # 등록은 이미 저장됐다. 기록이 실패해도 되돌릴 수는 없으므로 호출한 쪽에는 성공을 알리고 실패는 로그로 남긴다.
    _record(
        user,
        ACTION_COMPANY_CREATE,
        company_id,
        detail={"name": name, "dart_code": dart_code, "default_share_enabled": share},
    )
    return {
        "company_id": company_id,
        "name": name,
        "dart_code": dart_code,
        "default_share_enabled": share,
        "status": "success",
        "message": "계열사가 추가되었습니다.",
    }


def set_dart_code(user: dict, company_id: str, dart_code: str) -> dict:
    """A-07 계열사의 DART 고유번호를 입력·수정한다 (비우면 입력 전으로 되돌린다).

    user: 로그인 사용자. 최종 어드민만 할 수 있다
    company_id: 대상 회사 코드
    dart_code: DART 고유번호 숫자 8자리. 빈 문자열이면 지운다
    반환: {"company_id", "dart_code", "status": "success", "message": ...}
    PermissionError: 최종 어드민이 아닐 때
    ValueError: 형식이 틀렸거나 다른 계열사가 쓰는 번호일 때
    LookupError: 없는 계열사일 때
    """
    _require_super_admin(user, ACTION_COMPANY_UPDATE)
    dart_code = validators.validate_dart_code(dart_code)
    company = company_repository.get_company(company_id)
    if company is None:
        raise LookupError("계열사를 찾을 수 없습니다.")

    try:
        company_repository.update_dart_code(company_id, dart_code)
    except DuplicateCompanyError as exc:
        raise ValueError(_DUPLICATE_MESSAGES[exc.kind]) from exc
    _record(
        user,
        ACTION_COMPANY_UPDATE,
        company_id,
        detail={"dart_code": dart_code, "previous": company["dart_code"]},
    )
    return {
        "company_id": company_id,
        "dart_code": dart_code,
        "status": "success",
        "message": "DART 고유번호가 저장되었습니다.",
    }


def _require_super_admin(user: dict | None, action: str | None = None) -> None:
    """최종 어드민이 아니면 PermissionError (로그인 전도 포함).

    action 을 주면, 막힌 시도를 그 행위의 차단 기록으로 감사 로그에 남긴다 (누가 계열사 관리에 접근하려 했는지 알 수 있게).
    """
    if not user or user.get("role") != ROLE_SUPER_ADMIN:
        error = PermissionError("최종 어드민만 계열사를 관리할 수 있습니다.")
        if action:
            _record(user or {}, action, None, blocked=True, reason=str(error))
        raise error


def _record(
    user: dict,
    action: str,
    company_id: str | None,
    *,
    blocked: bool = False,
    reason: str | None = None,
    detail: dict | None = None,
) -> None:
    """감사 로그를 남긴다. 기록 실패가 원래 결과(성공·권한 오류)를 가리지 않도록 로그만 남기고 넘어간다."""
    try:
        record_audit_log(
            user.get("id"),
            action,
            company_id,
            None,  # ip_address: 명세 시그니처만 맞춘다. audit_logs 에 IP 컬럼이 없어 저장되지 않는다
            blocked,
            reason,
            target_type="company",
            context_detail=detail,
        )
    except Exception:
        logger.exception("A-07 감사 로그 기록 실패: action=%s company_id=%s", action, company_id)


def _to_company(row: dict) -> dict:
    """DB 행을 화면이 쓰는 계열사 dict 로 바꾼다 (0/1 → bool)."""
    return {
        **row,
        "is_active": bool(row["is_active"]),
        "default_share_enabled": bool(row["default_share_enabled"]),
    }
