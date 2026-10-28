"""A-07 계열사 등록·조회·수정.

A-07 계열사 동적 추가 = 최종 어드민이 새 회사를 등록하면 필터·권한·보고서 대상에 바로 들어가게 하는 기능이다.
회사는 고정 목록이 아니라 companies 테이블에서 읽는다 (docs/architecture/data-model.md). 다른 화면(검색 필터 등)은
회사 목록을 직접 적지 말고 get_company_options() 를 불러 쓴다.

역할 분담
- 이 파일(services): 최종 어드민 권한 확인, 입력 검증 호출, 중복 오류를 쉬운 문구로 바꾸기, 결과 모양 만들기.
- validators: 입력값 형식 검증 / company_repository: SQL 실행만 한다.

권한 (docs/architecture/overview.md §2.2): 계열사 추가·DART 설정은 최종 어드민만 할 수 있다.
"""

from app.admin import validators
from app.admin.repositories import company_repository
from app.admin.repositories.company_repository import DuplicateCompanyError
from core.constants import ROLE_SUPER_ADMIN

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
    # 권한 확인이 입력 검증·DB 접근보다 먼저다.
    _require_super_admin(user)
    name = validators.validate_company_name(name)
    company_id = validators.validate_company_code(company_id)
    dart_code = validators.validate_dart_code(dart_code)
    share = bool(default_share_enabled)

    try:
        company_repository.insert_company(company_id, name, dart_code, share)
    except DuplicateCompanyError as exc:
        raise ValueError(_DUPLICATE_MESSAGES[exc.kind]) from exc
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
    _require_super_admin(user)
    dart_code = validators.validate_dart_code(dart_code)
    if company_repository.get_company(company_id) is None:
        raise LookupError("계열사를 찾을 수 없습니다.")

    try:
        company_repository.update_dart_code(company_id, dart_code)
    except DuplicateCompanyError as exc:
        raise ValueError(_DUPLICATE_MESSAGES[exc.kind]) from exc
    return {
        "company_id": company_id,
        "dart_code": dart_code,
        "status": "success",
        "message": "DART 고유번호가 저장되었습니다.",
    }


def _require_super_admin(user: dict | None) -> None:
    """최종 어드민이 아니면 PermissionError (로그인 전도 포함)."""
    if not user or user.get("role") != ROLE_SUPER_ADMIN:
        raise PermissionError("최종 어드민만 계열사를 관리할 수 있습니다.")


def _to_company(row: dict) -> dict:
    """DB 행을 화면이 쓰는 계열사 dict 로 바꾼다 (0/1 → bool)."""
    return {
        **row,
        "is_active": bool(row["is_active"]),
        "default_share_enabled": bool(row["default_share_enabled"]),
    }
