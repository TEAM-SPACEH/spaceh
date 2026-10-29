"""A-03 공유 변경, A-05 권한 승인·반려.

A-03 그룹사 공유 = 한 계열사의 internal 문서를 다른 계열사 사용자도 볼 수 있게 여는 스위치다.
기본은 OFF 이고, 관리자 페이지에서만 바꾼다. 바꾸면 S-03 권한 필터가 보는 값(MySQL·Chroma)이 함께 바뀌어
검색·원문 보기에 바로 반영된다 (docs/architecture/overview.md §2).

역할 분담
- 이 파일(services): 관리 권한·보안 등급 확인, 감사 로그 기록, 결과 모양 만들기.
- access_repository(repositories): SQL 실행과 Chroma 갱신만 한다. 권한은 판단하지 않는다.

관리 권한 (overview §2.2)
- 계열사 관리자: 자사 internal 문서만.
- 최종 어드민: 전체 internal 문서.
- confidential 은 공유할 수 없다 (계약 단가 등). 열람 승인(A-05)으로만 연다.

이 파일을 A-03(이승준)과 A-05(정재연)가 함께 쓴다. 충돌을 줄이려고 구역을 나눈다.
- A-03: 이 파일의 공개 함수(get_manageable_documents·get_share_summary·set_group_share 등)와 "_" 보조 함수.
- A-05: 권한 승인·반려 함수는 set_group_share 아래의 "A-05" 구역에 추가하고, 보조 함수는 이름을 구분해서 둔다
  (예: _review_*). A-03 함수의 시그니처와 동작은 바꾸지 않는다. 바꿔야 하면 먼저 알린다.
"""

import logging
import math
import threading
from datetime import datetime

from app.admin.paging import as_int, clamp
from app.admin.repositories import access_repository
from app.admin.services.audit_service import KST, record_audit_log
from core.constants import (
    ACCESS_CONFIDENTIAL,
    ACCESS_INTERNAL,
    ROLE_COMPANY_ADMIN,
    ROLE_SUPER_ADMIN,
)

logger = logging.getLogger(__name__)

# 공유 변경을 한 번에 하나씩만 실행하게 하는 잠금(lock = "지금 내가 쓰는 중"이라는 표시).
# 같은 문서의 켜기·끄기 요청이 겹치면 두 요청이 각자 읽은 옛 값을 믿고 MySQL·Chroma 를 서로 다른 순서로 갱신해,
# 끈 문서가 타사 직원 검색에 남을 수 있다 (실제 MySQL·Chroma 로 재현: 겹친 40번 중 38번 어긋남).
# 이 잠금은 한 프로세스(서버) 안의 요청만 직렬화한다. 서버를 여러 개 띄우면 분산 잠금이 필요하다.
_GROUP_SHARE_LOCK = threading.Lock()

# documents.index_status 값 중 색인이 끝난 상태. 이때만 공유를 바꿀 수 있다 (docs/architecture/data-model.md).
INDEX_STATUS_DONE = "done"

# audit_logs.action 값. 스키마 정의서의 행위 코드(share_change)를 그대로 쓴다.
ACTION_SHARE_CHANGE = "share_change"

# 공유 설정 화면에는 public 문서가 필요 없다 (이미 전 사원이 본다).
SHARE_TARGET_LEVELS = (ACCESS_INTERNAL, ACCESS_CONFIDENTIAL)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_DATE_FORMAT = "%Y-%m-%d"


def get_manageable_documents(
    user: dict,
    keyword: str = "",
    company_filter: str = "",
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    *,
    share_filter: bool | None = None,
    access_level: str = "",
) -> dict:
    """A-03 관리자 범위 안에서 공유 설정 대상(internal·confidential) 문서를 최신순으로 한 페이지 조회한다.

    user: 로그인 사용자. {"role": ..., "company_id": ...} 모양
    keyword: 문서 제목이나 파일명에 포함된 글자
    company_filter: 계열사 코드. 최종 어드민만 적용된다 (계열사 관리자는 항상 자사 문서만)
    page, size: 페이지 번호(1부터)와 한 페이지 건수
    share_filter: 메소드 명세서에는 없는 선택 인자. True 면 공유 ON, False 면 공유 OFF 문서만, None 이면 전체
    access_level: 메소드 명세서에는 없는 선택 인자. internal 또는 confidential 이면 그 등급만. 그 밖의 값은 전체
    반환: {"documents": 문서 목록, "total_count": 조건 전체 건수, "page": 실제 페이지, "total_pages": 전체 페이지 수}
        문서 dict: doc_id, company_id, title, file_name, file_format, doc_type, access_level, is_group_shared(bool),
            chunk_count, index_status, created_at(문자열)
    PermissionError: 관리자가 아니거나, 소속 없는 계열사 관리자일 때
    """
    # 권한 확인이 DB 조회보다 먼저다. 계열사 관리자의 조회 범위(자사)는 화면이 보낸 company_filter 가 아니라
    # 여기서 user 정보로 정한다. 화면 값을 믿으면 값을 조작해 타사 문서를 볼 수 있기 때문이다.
    scope_company = _resolve_scope(user, company_filter)
    # 화면에서 온 값이 이상해도(0, 음수, 너무 큰 수, 글자) 안전한 범위로 보정한다.
    size = clamp(size, 1, MAX_PAGE_SIZE)
    page = max(as_int(page, 1), 1)
    keyword = (keyword or "").strip()

    # 첫 조회와 "마지막 페이지로 보정 후 재조회"가 같은 조건을 쓰도록 한 번만 만든다.
    # 화면이 보낸 등급이 공유 설정 대상(internal·confidential)일 때만 그 등급으로 좁힌다.
    levels = (access_level,) if access_level in SHARE_TARGET_LEVELS else SHARE_TARGET_LEVELS
    conditions = {
        "access_levels": levels,
        "company_id": scope_company,
        "keyword": keyword,
        "is_group_shared": share_filter,
    }
    rows, total = access_repository.list_documents(**conditions, limit=size, offset=(page - 1) * size)
    total_pages = max(math.ceil(total / size), 1)

    # 필터를 바꾸면 전체 건수가 줄어 현재 페이지가 범위를 벗어날 수 있다. 마지막 페이지로 다시 읽는다.
    if page > total_pages:
        page = total_pages
        rows, total = access_repository.list_documents(**conditions, limit=size, offset=(page - 1) * size)

    return {
        "documents": [_to_document(row) for row in rows],
        "total_count": total,
        "page": page,
        "total_pages": total_pages,
    }


def get_share_summary(user: dict, company_filter: str = "") -> dict:
    """A-03 공유 설정 화면 위쪽 카드용 집계. 관리 범위(계열사 관리자는 자사, 최종 어드민은 선택한 계열사 또는 전체) 안에서 센다.

    메소드 명세서에는 없는 보조 함수다.
    반환: {"shared": 공유 ON 사내 문서 수, "unshared": 공유 OFF 사내 문서 수, "confidential": 공유 불가 기밀 문서 수,
           "internal_total": 사내 문서 전체 수}
    PermissionError: 관리자가 아니거나, 소속 없는 계열사 관리자일 때
    """
    # 권한 확인이 DB 조회보다 먼저다. 조회 범위도 get_manageable_documents 와 같은 규칙으로 정한다.
    counts = access_repository.count_share_status(_resolve_scope(user, company_filter))
    return {**counts, "internal_total": counts["shared"] + counts["unshared"]}


def get_share_scope_name(user: dict) -> str:
    """A-03 화면 제목 위에 보여 줄 관리 범위 이름. 계열사 관리자는 회사명, 최종 어드민은 "전체 계열사".

    메소드 명세서에는 없는 보조 함수다.
    PermissionError: 관리자가 아니거나, 소속 없는 계열사 관리자일 때
    """
    company_code = _resolve_scope(user, "")
    if company_code is None:
        return "전체 계열사"
    # 회사명을 못 찾으면(삭제 등) 코드를 그대로 보여 준다.
    return access_repository.get_company_name(company_code) or company_code


def get_company_filter_options(user: dict) -> list[str]:
    """A-03 최종 어드민이 고를 수 있는 계열사 코드 목록을 돌려준다.

    메소드 명세서에는 없는 보조 함수다. 계열사 선택 드롭다운을 만들려고 쓴다.
    계열사 관리자는 자사 문서만 보므로 빈 목록을 돌려준다.
    PermissionError: 관리자가 아닐 때
    """
    # 계열사를 고르지 않았을 때 범위가 None(전체)인 사람이 최종 어드민이다. 세션의 role 이 아니라 DB 의 현재 값으로 판단한다.
    if _resolve_scope(user, "") is not None:
        return []
    return access_repository.list_company_ids()


def set_group_share(doc_id: str, share_enabled: bool, user: dict) -> dict:
    """A-03 문서 1건의 그룹사 공유를 켜거나 끈다. MySQL 과 Chroma 를 함께 바꾸고 감사 로그를 남긴다.

    doc_id: 대상 문서 ID
    share_enabled: True 면 공유 ON, False 면 OFF
    user: 로그인 사용자 (관리자)
    반환: {"doc_id": ..., "is_group_shared": bool, "status": "success", "message": "공유 설정이 변경되었습니다."}
    PermissionError: 관리자가 아니거나, 계열사 관리자가 타사 문서를 바꾸려 할 때
    ValueError: internal 이 아닌 문서(기밀 등)이거나, 색인이 끝나지 않은 문서일 때
    LookupError: 없는 문서일 때

    권한·등급 때문에 막힌 시도도 감사 로그에 남긴다 (blocked=True).
    """
    share_enabled = bool(share_enabled)
    user = user or {}
    session_user = user

    # 문서를 읽는 순간부터 저장이 끝날 때까지 한 번에 하나만 실행한다. 읽은 값(document)이 저장할 때까지 유효해야
    # 하고(이전 값으로 되돌리기), 두 저장소의 갱신 순서가 다른 요청과 섞이지 않아야 한다.
    # 감사 로그 기록은 잠금 밖에서 한다 (잠금을 오래 쥐지 않으려고).
    with _GROUP_SHARE_LOCK:
        # 1단계 검증: 바꾸기 전에 (1) 관리자인가 → (2) 문서가 있는가 → (3) 내 회사 문서이고 internal 인가 순으로 본다.
        # 관리자 확인이 가장 먼저라서 일반 사원은 문서가 있는지조차 알 수 없다.
        try:
            # 세션의 역할·소속은 로그인 뒤 바뀌었을 수 있다 (강등·소속 변경). 권한 판단은 DB 의 현재 값으로 한다.
            user = _refresh_user(user)
            _require_admin(user)
            document = access_repository.get_document(doc_id)
            if document is None:
                raise LookupError(f"문서를 찾을 수 없습니다: {doc_id}")
            _check_can_change(document, user)
        except (PermissionError, ValueError) as exc:
            # 감사 로그는 "막힌 시도"도 남긴다 (A-04). 누가 어떤 문서의 공유를 바꾸려다 막혔는지 관리자가 볼 수 있다.
            # LookupError 는 존재하지 않는 문서라 남길 대상이 없어 기록하지 않는다.
            _record(session_user, doc_id, blocked=True, reason=str(exc))
            raise

        # 2단계: 실제 변경. MySQL 과 Chroma 를 함께 바꾸고(실패해도 검색이 더 넓게 열리지 않는 순서), 실패하면 예외가 그대로 올라간다.
        # 시각은 감사 로그와 같은 기준(KST)으로 만든다. DATETIME 컬럼은 시간대를 저장하지 못해 tzinfo 를 뗀다.
        # 앞에서 읽은 document 를 넘겨, 저장소가 중간에 실패했을 때 이전 값으로 되돌릴 수 있게 한다.
        access_repository.update_group_share(
            doc_id, share_enabled, user.get("id"), datetime.now(KST).replace(tzinfo=None), document
        )
    # 공유 값은 이미 커밋됐다. 기록이 실패해도 바뀐 값을 되돌릴 수는 없으므로, 호출한 쪽에는 성공을 알리고
    # 실패는 로그에 남겨 운영자가 알 수 있게 한다.
    _record(
        session_user,
        doc_id,
        blocked=False,
        reason=None,
        document=document,
        detail={"is_group_shared": share_enabled, "previous": bool(document["is_group_shared"])},
    )
    return {
        "doc_id": doc_id,
        "is_group_shared": share_enabled,
        "status": "success",
        "message": "공유 설정이 변경되었습니다.",
    }


def _refresh_user(user: dict) -> dict:
    """세션에 저장된 user 의 역할·소속을 DB 의 현재 값으로 바꿔 돌려준다 (id 등 나머지 값은 그대로).

    세션 값을 믿으면 로그인한 뒤 강등되거나 다른 계열사로 옮겨진 관리자가 옛 권한으로 계속 조회·변경할 수 있다.
    ID 가 없거나 계정이 없거나 비활성이면 역할을 None 으로 둬서 아래 관리자 확인에서 거부된다.
    """
    user_id = user.get("id")
    current = access_repository.find_active_user(user_id) if type(user_id) is int else None
    current = current or {"role": None, "company_id": None}
    return {**user, "role": current["role"], "company_id": current["company_id"]}


def _require_admin(user: dict) -> None:
    """관리자(계열사 관리자·최종 어드민)가 아니면 PermissionError."""
    if user.get("role") not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        raise PermissionError("관리자만 공유 설정을 변경할 수 있습니다.")


def _check_can_change(document: dict, user: dict) -> None:
    """이 관리자가 이 문서의 공유를 바꿀 수 있는지 확인한다. 안 되면 PermissionError·ValueError."""
    # 최종 어드민은 회사 제한이 없어 이 검사를 건너뛴다.
    if user["role"] == ROLE_COMPANY_ADMIN:
        # 소속이 없으면 None == None 이 참이 되지 않도록 값이 있는지부터 본다.
        if not user.get("company_id") or document["company_id"] != user["company_id"]:
            raise PermissionError("자사 문서만 공유 설정을 변경할 수 있습니다.")
    # 등급 검사는 역할과 무관하게 모두에게 적용한다. 최종 어드민도 기밀는 공유할 수 없다.
    # (DB 에도 ck_documents_shared_internal 제약이 있어 한 번 더 막히지만, 쉬운 안내 문구를 주려고 먼저 본다.)
    level = document["access_level"]
    if level == ACCESS_CONFIDENTIAL:
        raise ValueError("기밀(confidential) 문서는 그룹사에 공유할 수 없습니다.")
    if level != ACCESS_INTERNAL:
        raise ValueError("사내(internal) 문서만 그룹사에 공유할 수 있습니다.")
    # 색인이 끝나지 않은 문서(대기·색인 중·실패)는 바꾸지 못하게 한다. 색인은 청크를 업로드 당시의 공유 값으로 저장하므로,
    # 그 사이에 바꾼 값이 Chroma 에 반영되지 않거나 나중에 덮어써져 검색 권한이 MySQL 과 어긋날 수 있다.
    if document["index_status"] != INDEX_STATUS_DONE:
        raise ValueError("색인이 끝난 문서만 공유 설정을 바꿀 수 있습니다.")


def _record(
    user: dict,
    doc_id: str,
    blocked: bool,
    reason: str | None,
    document: dict | None = None,
    detail: dict | None = None,
) -> None:
    """감사 로그를 남긴다. 기록 실패가 원래 결과(성공·권한 오류)를 가리지 않도록 로그만 남기고 넘어간다."""
    try:
        record_audit_log(
            user.get("id"),
            ACTION_SHARE_CHANGE,
            doc_id,
            None,  # ip_address: 명세 시그니처만 맞춘다. audit_logs 에 IP 컬럼이 없어 저장되지 않는다
            blocked,
            reason,
            target_type="document",
            doc_ids=[doc_id],
            doc_companies=[document["company_id"]] if document else None,
            context_detail=detail,
        )
    except Exception:
        logger.exception("A-03 공유 변경 감사 로그 기록 실패: doc_id=%s", doc_id)


def _resolve_scope(user: dict | None, company_filter: str) -> str | None:
    """관리 권한을 확인하고 조회 범위(계열사 코드)를 돌려준다.

    반환: 계열사 코드(그 계열사 문서만) 또는 None(전체, 최종 어드민이 계열사를 고르지 않은 경우)
    PermissionError: 관리자가 아니거나 소속 없는 계열사 관리자
    """
    if not user:
        raise PermissionError("로그인이 필요합니다.")
    user = _refresh_user(user)
    role = user.get("role")
    if role == ROLE_SUPER_ADMIN:
        return company_filter or None
    if role == ROLE_COMPANY_ADMIN:
        company_id = user.get("company_id")
        # None(전체)으로 처리하면 권한이 넓어지므로 소속 없는 관리자는 거부한다.
        if not company_id:
            raise PermissionError("소속 계열사가 없는 관리자는 공유 설정을 볼 수 없습니다.")
        return company_id
    raise PermissionError("관리자만 공유 설정을 볼 수 있습니다.")


def _to_document(row: dict) -> dict:
    """DB 행을 화면이 쓰는 문서 dict 로 바꾼다 (is_group_shared 0/1 → bool, created_at → 문자열)."""
    created_at = row["created_at"]
    return {
        "doc_id": row["doc_id"],
        "company_id": row["company_id"],
        "title": row["title"],
        "file_name": row["file_name"],
        "file_format": row["file_format"],
        "doc_type": row["doc_type"],
        "access_level": row["access_level"],
        "is_group_shared": bool(row["is_group_shared"]),
        "chunk_count": row["chunk_count"],
        "index_status": row["index_status"],
        "created_at": created_at.strftime(_DATE_FORMAT) if isinstance(created_at, datetime) else str(created_at),
    }
