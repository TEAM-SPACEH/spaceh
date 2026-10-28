"""A-04 감사 로그 기록·조회: record_audit_log(), search_audit_logs() 외.

감사 로그 = "누가·언제·무엇을 했고, 막혔다면 왜 막혔는지"를 남기는 기록이다.
로그인·검색·원문 열람·다운로드처럼 권한이 걸리는 모든 행위를 차단된 것까지 포함해 남기며,
관리자는 이 기록으로 "누가 어떤 문서에 접근하려 했는지"를 되짚어 볼 수 있다.

역할 분담
- 이 파일(services): 권한 확인, 기록 시각(KST) 만들기, 화면에서 받은 조건 가공, 결과 모양 만들기.
- audit_repository(repositories): SQL 실행만 한다. 권한은 판단하지 않고 받은 값을 그대로 쓴다.

조회 권한 (docs/architecture/overview.md §2)
- 일반 사원: 조회 불가.
- 계열사 관리자: 자사 직원이 행동한 로그만 (행동 당시 소속이 자사). 타사 직원이 자사 문서를 건드린
  로그는 보이지 않는다 (범위 계산은 audit_repository._where).
- 최종 어드민: 전체.
"""

import csv
import io
import math
from datetime import date, datetime, time, timedelta, timezone

from app.admin.paging import as_int, clamp
from app.admin.repositories import audit_repository
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN

# 기록 시각의 기준 시간대. DB 서버 설정과 무관하게 한국 시간으로 남긴다.
KST = timezone(timedelta(hours=9))

# audit_logs.block_reason 컬럼 길이(VARCHAR(200)). 넘으면 INSERT 가 실패하므로 잘라서 넣는다.
BLOCK_REASON_MAX_LENGTH = 200

# 목록 한 페이지의 기본·최대 건수. 최대치는 화면 값이 이상해도 한 번에 너무 많이 읽지 않게 막는다.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 화면에 보여 주는 시각 형식 (예: 2026-10-27 09:30:05).
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 행위 코드(audit_logs.action)의 화면 이름. 목록에 없는 코드는 코드 그대로 보여 준다.
ACTION_LABELS = {
    "login": "로그인",
    "search": "검색",
    "ask": "질문",
    "view_document": "원문 열기",
    "download": "원문 내려받기",
    "report_create": "보고서 생성",
    "upload": "문서 업로드",
    "share_change": "공유 변경",
    "access_request": "권한 요청",
    "access_review": "권한 처리",
    "audit_export": "감사 로그 내려받기",
}

# 요약 카드의 시간대별 막대가 보여 주는 시각 범위 (업무 시간 9시~18시).
HOURLY_START, HOURLY_END = 9, 18

# CSV 로 한 번에 내려받을 수 있는 최대 건수. 너무 많은 로그가 한 번에 반출되지 않게 막는다.
EXPORT_MAX_ROWS = 5000

# 타사 문서는 제목을 보여 주지 않고 이 문구로 대신한다 (관리자가 볼 수 없는 문서의 제목 노출 방지).
OTHER_COMPANY_DOCUMENT = "타사 문서"


def record_audit_log(
    user_id: int | None,
    action_type: str,
    target_id: str | None,
    ip_address: str | None,
    blocked: bool,
    block_reason: str | None,
    *,
    employee_no: str | None = None,
    target_type: str | None = None,
    query: str | None = None,
    filters: dict | None = None,
    doc_ids: list | None = None,
    doc_companies: list | None = None,
    result_count: int | None = None,
    context_detail: dict | None = None,
) -> dict:
    """A-04 로그인·검색·열람 등 발생한 행위를 감사 로그 1건으로 기록한다.

    각 기능(로그인·검색·원문 보기 등)이 처리하는 도중에 부른다. 차단된 행위도 기록한다.
    앞의 6개 인자는 메소드 명세서 그대로이고, 나머지는 선택 인자라 안 넘겨도 된다.

    user_id: 행동한 사용자(users.id). 로그인 실패처럼 모르면 None
    action_type: 행위 코드. 영어 소문자 (login, search, ask, view_document, download,
        report_create, upload, share_change, access_request, access_review 등)
    target_id: 행위 대상 ID (문서 ID 등). 없으면 None
    ip_address: 명세 시그니처를 맞추려고 받지만 저장하지 않는다 (audit_logs 에 IP 컬럼이 없다)
    blocked: 권한 등으로 막힌 행위면 True
    block_reason: 차단 사유. 컬럼 길이(200자)를 넘으면 잘라서 저장한다
    employee_no: 사용자를 id 로 못 찾는 로그인 실패 때 입력된 사원번호
    target_type: 대상 종류 (document, report, user, company, access_request)
    query, filters: 검색어와 적용 필터
    doc_ids, doc_companies: 결과·근거 문서의 ID와 그 문서의 회사 코드 목록
    result_count: 결과 건수
    context_detail: 그 밖의 부가 정보
    반환: {"log_id": 새 로그 id, "status": "success"}

    DB 오류는 삼키지 않고 그대로 올린다. 호출하는 쪽이 "기록 실패"를 알아야 하기 때문이다.
    """
    if not action_type:
        raise ValueError("action_type 은 비어 있을 수 없습니다.")

    # 시각은 부르는 쪽이 아니라 여기서 정한다. 그래야 모든 기록이 같은 기준(KST)을 따른다.
    # tzinfo 를 떼는 이유: DATETIME 컬럼은 시간대 정보를 저장하지 못한다.
    created_at = datetime.now(KST).replace(tzinfo=None)

    log_id = audit_repository.insert_log(
        user_id=user_id,
        employee_no=employee_no,
        action=action_type,
        target_type=target_type,
        target_id=target_id,
        query=query,
        filters=filters,
        doc_ids=doc_ids,
        doc_companies=doc_companies,
        result_count=result_count,
        is_blocked=bool(blocked),
        block_reason=_cut_reason(block_reason),
        context_detail=context_detail,
        created_at=created_at,
    )
    return {"log_id": log_id, "status": "success"}


def search_audit_logs(
    user: dict,
    filters: dict | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """A-04 조회 권한과 조회 범위, 필터 조건을 적용해 감사 로그를 최신순으로 한 페이지 조회한다.

    user: 로그인 사용자. {"role": ..., "company_id": ...} 모양
    filters: 화면 필터. 모두 선택 사항이다.
        employee_no(사원번호), action_type(행위 코드), start_date·end_date(날짜, 종료일 포함),
        blocked_only(True 면 차단된 것만)
    page, size: 페이지 번호(1부터)와 한 페이지 건수
    반환: {"logs": 로그 목록, "total_count": 조건 전체 건수, "page": 실제 페이지, "total_pages": 전체 페이지 수}
    PermissionError: 조회 권한이 없을 때
    """
    company_code = _resolve_scope(user)
    filters = filters or {}
    size = clamp(size, 1, MAX_PAGE_SIZE)
    page = max(as_int(page, 1), 1)

    conditions = {
        "company_code": company_code,
        "employee_no": filters.get("employee_no") or None,
        "action": filters.get("action_type") or None,
        "start": _day_start(filters.get("start_date")),
        # 종료일은 "그날 끝까지" 포함해야 하므로 다음 날 0시 '미만'으로 비교한다.
        "end": _day_start(filters.get("end_date"), plus_days=1),
        "blocked_only": bool(filters.get("blocked_only")),
    }

    rows, total = audit_repository.search_logs(
        **conditions, limit=size, offset=(page - 1) * size
    )
    total_pages = max(math.ceil(total / size), 1)

    # 필터를 바꾸면 전체 건수가 줄어 현재 페이지가 범위를 벗어날 수 있다.
    # 빈 화면을 보여 주는 대신 마지막 페이지로 다시 읽는다.
    if page > total_pages:
        page = total_pages
        rows, total = audit_repository.search_logs(
            **conditions, limit=size, offset=(page - 1) * size
        )

    return {
        "logs": _enrich([_to_log(row) for row in rows], company_code),
        "total_count": total,
        "page": page,
        "total_pages": total_pages,
    }


def get_audit_log_detail(log_id: int, user: dict) -> dict:
    """A-04 조회 권한을 확인하고 감사 로그 1건의 상세를 조회한다.

    log_id: 조회할 로그 id
    user: 로그인 사용자
    반환: 로그 상세 dict (차단 사유·부가 정보 포함)
    PermissionError: 조회 권한이 없을 때
    LookupError: 없는 로그이거나 조회 범위 밖의 로그일 때. 두 경우를 구분하지 않는다
        (범위 밖 로그가 있다는 사실 자체를 알려 주지 않기 위해서다)
    """
    # 권한 확인이 DB 조회보다 먼저다. 권한 없는 사용자가 쿼리를 일으키지 못하게 한다.
    company_code = _resolve_scope(user)
    row = audit_repository.get_log(log_id, company_code)
    if row is None:
        raise LookupError(f"감사 로그를 찾을 수 없습니다: {log_id}")
    return _enrich([_to_log(row)], company_code)[0]


def get_recent_audit_logs(user: dict, limit: int = 10) -> list[dict]:
    """A-04 관리자 조회 범위 안의 최근 감사 로그를 지정한 건수만큼 조회한다 (대시보드용).

    user: 로그인 사용자
    limit: 가져올 건수. 1~100 으로 보정한다
    반환: 로그 dict 목록 (최신순)
    PermissionError: 조회 권한이 없을 때
    """
    company_code = _resolve_scope(user)
    rows = audit_repository.list_recent(company_code, clamp(limit, 1, MAX_PAGE_SIZE))
    return _enrich([_to_log(row) for row in rows], company_code)


def get_audit_filter_options(user: dict) -> dict:
    """A-04 조회 화면 필터의 선택지(사원번호·행위 코드)를 조회 범위 안에서 모은다.

    메소드 명세서에는 없는 보조 함수다. 필터 입력칸을 목록 선택으로 만들려고 쓴다.
    user: 로그인 사용자
    반환: {"users": [사원번호...], "action_types": [행위 코드...]}
    PermissionError: 조회 권한이 없을 때
    """
    company_code = _resolve_scope(user)
    return {
        "users": audit_repository.list_employee_nos(company_code),
        "action_types": audit_repository.list_actions(company_code),
    }


def get_audit_summary(user: dict, today: date | None = None) -> dict:
    """A-04 조회 범위 안의 오늘 로그를 요약한다 (감사 로그 화면 위쪽 카드용).

    메소드 명세서에는 없는 보조 함수다. 숫자는 모두 조회 범위(계열사 관리자는 자사 직원 로그) 안에서 센다.
    user: 로그인 사용자
    today: 기준 날짜. 안 주면 지금(KST)의 날짜. 시험에서 날짜를 고정하려고 둔 인자다
    반환: {"today_count": 오늘 건수, "yesterday_count": 어제 건수, "blocked_count": 오늘 차단 건수,
           "blocked_reasons": [(사유, 건수)...] 많은 순 최대 3개, "download_count": 오늘 원문 내려받기 건수,
           "blocked_download_count": 그중 차단 건수, "hourly": 9~18시 시간대별 건수 리스트(10개)}
    PermissionError: 조회 권한이 없을 때
    """
    company_code = _resolve_scope(user)
    today = today or datetime.now(KST).date()
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=1)
    day = audit_repository.summarize(company_code, start, end)
    previous = audit_repository.summarize(company_code, start - timedelta(days=1), start)
    return {
        "today_count": day["total"],
        "yesterday_count": previous["total"],
        "blocked_count": day["blocked"],
        "blocked_reasons": day["blocked_reasons"],
        "download_count": day["downloads"],
        "blocked_download_count": day["blocked_downloads"],
        "hourly": [day["hourly"].get(hour, 0) for hour in range(HOURLY_START, HOURLY_END + 1)],
    }


def get_audit_scope_name(user: dict) -> str:
    """A-04 화면 제목 위에 보여 줄 관리 범위 이름. 계열사 관리자는 회사명, 최종 어드민은 "전체 계열사".

    PermissionError: 조회 권한이 없을 때
    """
    company_code = _resolve_scope(user)
    if company_code is None:
        return "전체 계열사"
    # 회사명을 못 찾으면(삭제 등) 코드를 그대로 보여 준다.
    return audit_repository.get_company_name(company_code) or company_code


def export_audit_logs_csv(user: dict, filters: dict | None = None) -> str:
    """A-04 현재 필터에 맞는 로그를 조회 범위 안에서 CSV 문자열로 만든다 (최대 EXPORT_MAX_ROWS 건, 최신순).

    조회 화면과 같은 범위 규칙을 따르고, 내려받기 자체도 감사 로그(audit_export)에 남긴다.
    user: 로그인 사용자
    filters: search_audit_logs 와 같은 화면 필터
    반환: 엑셀에서 한글이 깨지지 않도록 BOM(바이트 순서 표시) 문자로 시작하는 CSV 텍스트
    PermissionError: 조회 권한이 없을 때
    """
    result = search_audit_logs(user, filters, page=1, size=MAX_PAGE_SIZE)
    logs = list(result["logs"])
    # 한 번에 읽는 최대치(MAX_PAGE_SIZE)보다 많이 내려받을 수 있게 다음 페이지를 이어서 읽는다.
    limit = min(result["total_count"], EXPORT_MAX_ROWS)
    page = 1
    while len(logs) < limit and page < result["total_pages"]:
        page += 1
        logs.extend(search_audit_logs(user, filters, page=page, size=MAX_PAGE_SIZE)["logs"])
    logs = logs[:limit]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["시각", "사원번호", "이름", "소속", "행위", "대상", "차단", "차단 사유"])
    for log in logs:
        values = (
            log["created_at"],
            log["employee_no"] or "",
            log["user_name"] or "",
            log["company_code"] or "",
            log["action_label"],
            log["target_label"],
            "차단" if log["blocked"] else "허용",
            log["block_reason"] or "",
        )
        writer.writerow([_csv_safe(value) for value in values])

    # 반출은 반드시 기록이 남아야 하므로, 기록이 실패하면 예외를 그대로 올려 파일을 주지 않는다.
    record_audit_log(
        user.get("id"),
        "audit_export",
        None,
        None,
        False,
        None,
        target_type="audit_log",
        filters=filters or None,
        result_count=len(logs),
    )
    return "\ufeff" + buffer.getvalue()


def _csv_safe(value) -> str:
    """CSV 셀 값을 문자열로 바꾸고, 엑셀이 수식으로 실행할 수 있는 시작 문자(= + - @ 탭 줄바꿈)는 ' 를 붙여 막는다.

    로그에는 사용자가 입력한 검색어·사유가 들어 있어서, 내려받은 파일을 엑셀로 열 때 수식이 실행될 수 있다.
    """
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _enrich(logs: list[dict], company_code: str | None) -> list[dict]:
    """로그 dict 에 화면용 값(user_name, action_label, target_label)을 더한다.

    company_code: 조회 범위. 자사 문서만 제목을 보여 주고, 그 밖의 회사 문서는 제목을 가린다 (None 이면 전체 공개).
    """
    user_names = audit_repository.lookup_user_names(
        sorted({log["user_id"] for log in logs if log["user_id"] is not None})
    )
    documents = audit_repository.lookup_documents(
        sorted({log["target_id"] for log in logs if log["target_type"] == "document" and log["target_id"]})
    )
    for log in logs:
        log["user_name"] = user_names.get(log["user_id"])
        log["action_label"] = ACTION_LABELS.get(log["action_type"], log["action_type"])
        log["target_label"] = _target_label(log, documents, company_code)
    return logs


def _target_label(log: dict, documents: dict, company_code: str | None) -> str:
    """"대상" 칸에 보여 줄 글자: 문서 제목 > 검색어·질문 > 대상 ID > "-"."""
    if log["target_type"] == "document" and log["target_id"]:
        document = documents.get(log["target_id"])
        if document is None:
            return "삭제된 문서"
        if company_code is None or document["company_id"] == company_code:
            return document["title"]
        return OTHER_COMPANY_DOCUMENT
    return log["query"] or log["target_id"] or "-"


def _resolve_scope(user: dict | None) -> str | None:
    """조회 권한을 확인하고 조회 범위(계열사 코드)를 돌려준다.

    반환: 계열사 코드(그 계열사 범위만 조회) 또는 None(전체 조회, 최종 어드민)
    PermissionError: 일반 사원·로그인 전, 소속 없는 계열사 관리자
    """
    if not user:
        raise PermissionError("로그인이 필요합니다.")
    role = user.get("role")
    if role == ROLE_SUPER_ADMIN:
        return None
    if role == ROLE_COMPANY_ADMIN:
        company_id = user.get("company_id")
        # 소속이 없으면 범위를 정할 수 없다. 이때 None(전체)으로 처리하면 권한이
        # 넓어지므로 거부한다.
        if not company_id:
            raise PermissionError("소속 계열사가 없는 관리자는 감사 로그를 조회할 수 없습니다.")
        return company_id
    raise PermissionError("감사 로그는 관리자만 조회할 수 있습니다.")


def _cut_reason(reason: str | None) -> str | None:
    """차단 사유를 컬럼 길이(BLOCK_REASON_MAX_LENGTH)로 자른다. 비어 있으면 None."""
    if not reason:
        return None
    return reason[:BLOCK_REASON_MAX_LENGTH]


def _day_start(value: date | None, plus_days: int = 0) -> datetime | None:
    """날짜를 그날 0시 datetime 으로 바꾼다 (plus_days 만큼 미룰 수 있다). 값이 없으면 None."""
    if value is None or value == "":
        return None
    # datetime 은 date 의 하위 클래스라 시각이 붙어 있으면 날짜만 남긴다.
    if isinstance(value, datetime):
        value = value.date()
    return datetime.combine(value, time.min) + timedelta(days=plus_days)


def _to_log(row: dict) -> dict:
    """DB 행을 화면·다른 서비스가 쓰는 로그 dict 로 바꾼다.

    id → log_id, action → action_type, is_blocked(0/1) → blocked(True/False),
    created_at → 문자열. IP 는 저장하지 않으므로 없다.
    """
    created_at = row["created_at"]
    return {
        "log_id": row["id"],
        "created_at": created_at.strftime(_TIME_FORMAT)
        if isinstance(created_at, datetime)
        else str(created_at),
        "user_id": row["user_id"],
        "employee_no": row["employee_no"],
        "role": row["role"],
        "company_code": row["company_code"],
        "action_type": row["action"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "query": row["query"],
        "filters": row["filters"],
        "doc_ids": row["doc_ids"],
        "doc_companies": row["doc_companies"],
        "result_count": row["result_count"],
        "blocked": bool(row["is_blocked"]),
        "block_reason": row["block_reason"],
        "context_detail": row["context_detail"],
    }
