"""M-04 내 사용 히스토리: get_user_history(), get_history_detail(), rerun_search(),
get_history_report(), get_access_request_history().

이력은 A-04 감사 로그(audit_logs)에서 본인 행만 읽는다. 별도 이력 테이블은 없다.
모든 함수는 요청한 user_id 가 지금 로그인한 사용자일 때만 동작한다 (남의 이력은 열지 않는다).

검색 재실행과 보고서 다시 열기는 "그때" 권한이 아니라 "지금" 권한으로 다시 확인한다.
그 사이 공유가 꺼지거나 승인이 취소됐을 수 있기 때문이다 (overview.md §2.3-4).
"""

import logging

from app.auth.session import get_current_user_id
from app.history.repositories import history_repository
from app.permissions.services.permission_service import check_search_permission
from app.search.services.search_service import hybrid_search
from app.users.services.user_service import get_user_info

logger = logging.getLogger(__name__)

# 히스토리에 보여 줄 이력 유형 = audit_logs.action 코드 → 화면 이름. 순서대로 탭을 그린다.
HISTORY_TYPES = {
    "search": "검색",
    "ask": "질문",
    "view_document": "원문 열람",
    "report_create": "보고서 생성",
}

# 감사 로그에서 읽는 유형. 보고서 생성은 감사 로그 대신 reports 테이블에서 바로 읽는다.
# 보고서 다시 열기도 reports 를 읽으므로 목록과 열기가 같은 곳을 보게 된다.
_LOG_ACTIONS = ["search", "ask", "view_document"]

# 다시 검색할 수 있는 유형. 통합 검색 화면은 검색과 AI 답변을 한 번에 하고 ask 로만 기록하므로 (#100)
# ask 도 search 와 같이 저장된 검색어·필터로 다시 검색한다.
_RERUN_ACTIONS = ["search", "ask"]

# 한 번에 읽는 이력 최대 건수. 오래 쓴 계정도 화면이 느려지지 않게 최신 것만 본다.
HISTORY_LIMIT = 100

# 권한 요청 상태(access_requests.status) → 화면 이름
REQUEST_STATUS_LABELS = {
    "pending": "대기",
    "approved": "승인",
    "rejected": "반려",
}

_TIME_FORMAT = "%Y-%m-%d %H:%M"


def get_user_history(user_id: int, history_type: str | None) -> list[dict]:
    """M-04 로그인 사용자의 검색·질문·원문 열람·보고서 생성 이력을 최신순으로 조회한다.

    history_type: HISTORY_TYPES 의 키. None 이면 전체. 모르는 값이면 빈 목록
    반환: [{"history_id", "history_type", "type_label", "summary", "created_at",
            "result_count", "is_blocked", "can_rerun", "report_id"}, ...]
        summary 는 검색어·질문, 열람한 문서 제목, 보고서 제목 중 하나다.
        보고서 항목은 감사 로그가 아니라서 history_id 가 None 이고 report_id 로 연다.
    """
    if not _is_self(user_id):
        return []
    if history_type is None:
        actions, with_reports = list(_LOG_ACTIONS), True
    elif history_type == "report_create":
        actions, with_reports = [], True
    elif history_type in HISTORY_TYPES:
        actions, with_reports = [history_type], False
    else:
        return []

    rows = history_repository.list_user_logs(user_id, actions, HISTORY_LIMIT)
    documents = history_repository.find_documents(
        sorted({row["target_id"] for row in rows if row["action"] == "view_document" and row["target_id"]})
    )
    dated = [(row["created_at"], _to_item(row, documents)) for row in rows]
    if with_reports:
        dated += [(report["created_at"], _report_item(report))
                  for report in history_repository.list_user_reports(user_id, HISTORY_LIMIT)]

    # 감사 로그와 보고서를 합쳐 최신순으로 다시 세운다. 시각은 표시용 문자열이 아니라 원래 값으로 비교한다.
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in dated[:HISTORY_LIMIT]]


def get_history_detail(user_id: int, history_id: int) -> dict | None:
    """M-04 선택한 사용 이력의 검색어, 질문 내용, 문서 정보 및 실행 시점 등 상세 정보를 조회한다.

    반환: get_user_history() 항목에 "query", "filters", "documents"([{"doc_id", "title"}]),
        "block_reason" 을 더한 dict. 본인 이력이 아니거나 없으면 None
    """
    if not _is_self(user_id):
        return None
    row = history_repository.get_user_log(user_id, history_id, _LOG_ACTIONS)
    if row is None:
        return None

    doc_ids = list(row.get("doc_ids") or [])
    if row["action"] == "view_document" and row["target_id"] and row["target_id"] not in doc_ids:
        doc_ids.insert(0, row["target_id"])
    documents = history_repository.find_documents(doc_ids)

    detail = _to_item(row, documents)
    detail.update(
        {
            "query": row.get("query"),
            "filters": row.get("filters"),
            # 지금은 지워진 문서도 기록에는 남아 있으므로 제목 대신 id 를 보여 준다.
            "documents": [
                {"doc_id": doc_id, "title": documents[doc_id]["title"] if doc_id in documents else doc_id}
                for doc_id in doc_ids
            ],
            "block_reason": row.get("block_reason"),
        }
    )
    return detail


def rerun_search(user_id: int, history_id: int) -> dict:
    """M-04 과거 검색어와 필터 조건을 불러와 현재 사용자 권한을 다시 적용하여 검색을 재실행한다.

    검색(search)과 질문(ask) 이력 모두 저장된 검색어·필터로 다시 검색한다.
    반환: {"history_id", "query", "filters", "results"}. results 는 hybrid_search() 결과 그대로.
        본인 검색 이력이 아니거나 사용자 정보를 못 읽으면 빈 dict
    오류: 검색 중 오류(Chroma·임베딩)는 그대로 올린다. 화면이 안내한다
    """
    if not _is_self(user_id):
        return {}
    row = history_repository.get_user_log(user_id, history_id, _RERUN_ACTIONS)
    if row is None or not (row.get("query") or "").strip():
        return {}
    user = _current_user(user_id)
    if user is None:
        return {}

    # 저장된 결과(doc_ids)를 다시 보여 주지 않는다. 지금 권한으로 검색을 새로 해야
    # 그 사이 볼 수 없게 된 문서가 섞이지 않는다.
    filters = row.get("filters") or None
    return {
        "history_id": history_id,
        "query": row["query"],
        "filters": filters,
        "results": hybrid_search(row["query"], filters, user),
    }


def get_history_report(user_id: int, report_id: int) -> dict | None:
    """M-04 과거에 생성한 보고서를 조회하고 현재 접근 권한을 검증한 뒤 반환한다.

    근거 문서 중 하나라도 지금 볼 수 없거나 지워졌으면 열지 않는다 (None).
    보고서 본문에 그 문서 내용이 들어 있기 때문이다.
    반환: {"report_id", "title", "template", "params", "content_md", "footnotes",
            "exec_summary_md", "doc_ids", "max_access_level", "created_at"} 또는 None
    """
    if not _is_self(user_id):
        return None
    report = history_repository.find_user_report(user_id, report_id)
    if report is None:
        return None
    user = _current_user(user_id)
    if user is None:
        return None

    doc_ids = list(report.get("doc_ids") or [])
    documents = history_repository.find_documents(doc_ids)
    if any(not check_search_permission(user, documents.get(doc_id)) for doc_id in doc_ids):
        logger.info("M-04 보고서 열람 불가 report_id=%s user_id=%s", report_id, user_id)
        return None

    return {
        "report_id": report["id"],
        "title": report["title"],
        "template": report["template"],
        "params": report.get("params"),
        "content_md": report["content_md"],
        "footnotes": report.get("footnotes") or [],
        "exec_summary_md": report.get("exec_summary_md"),
        "doc_ids": doc_ids,
        "max_access_level": report["max_access_level"],
        "created_at": _format_time(report["created_at"]),
    }


def get_access_request_history(user_id: int) -> list[dict]:
    """M-04 사용자가 신청한 문서 열람 요청의 대기·승인·반려 상태 및 반려 사유를 최신순으로 조회한다.

    반환: [{"request_id", "doc_id", "title", "owner_company_code", "reason", "status",
            "status_label", "review_comment", "created_at", "reviewed_at"}, ...]
    """
    if not _is_self(user_id):
        return []
    return [
        {
            "request_id": row["id"],
            "doc_id": row["doc_id"],
            "title": row.get("title") or row["doc_id"],
            "owner_company_code": row["owner_company_code"],
            "reason": row["reason"],
            "status": row["status"],
            "status_label": REQUEST_STATUS_LABELS.get(row["status"], row["status"]),
            "review_comment": row.get("review_comment"),
            "created_at": _format_time(row["created_at"]),
            "reviewed_at": _format_time(row.get("reviewed_at")),
        }
        for row in history_repository.list_access_requests(user_id)
    ]


def _is_self(user_id: int) -> bool:
    """요청한 user_id 가 지금 로그인한 사용자인지. 남의 id 로 이력을 열지 못하게 막는다."""
    if user_id is None or user_id != get_current_user_id():
        logger.info("M-04 본인이 아닌 user_id 요청 거부")
        return False
    return True


def _current_user(user_id: int) -> dict | None:
    """권한 확인용 사용자 정보. 세션 값이 아니라 DB 의 지금 역할·소속을 쓴다."""
    info = get_user_info(user_id)
    if info is None:
        return None
    return {"id": info["user_id"], "role": info["role"], "company_id": info["company_id"]}


def _to_item(row: dict, documents: dict) -> dict:
    """감사 로그 행 → 히스토리 목록 항목."""
    action = row["action"]
    if action == "view_document":
        document = documents.get(row["target_id"])
        summary = document["title"] if document else (row["target_id"] or "")
    else:
        summary = row.get("query") or ""
    return {
        "history_id": row["id"],
        "history_type": action,
        "type_label": HISTORY_TYPES.get(action, action),
        "summary": summary,
        "created_at": _format_time(row["created_at"]),
        "result_count": row.get("result_count"),
        "is_blocked": bool(row.get("is_blocked")),
        "can_rerun": action in _RERUN_ACTIONS and bool((row.get("query") or "").strip()),
        "report_id": None,
    }


def _report_item(report: dict) -> dict:
    """reports 행 → 히스토리 목록 항목. 감사 로그가 아니라서 history_id 는 없다."""
    return {
        "history_id": None,
        "history_type": "report_create",
        "type_label": HISTORY_TYPES["report_create"],
        "summary": report["title"],
        "created_at": _format_time(report["created_at"]),
        "result_count": None,
        "is_blocked": False,
        "can_rerun": False,
        "report_id": report["id"],
    }


def _format_time(value) -> str | None:
    return value.strftime(_TIME_FORMAT) if value else None
