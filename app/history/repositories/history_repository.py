"""M-04 내 사용 히스토리 DB 읽기 (repositories 계층).

사용 이력은 별도 테이블 없이 audit_logs 에서 본인 행만 읽는다 (data-model.md).
모든 조회에 user_id 조건을 건다. 다른 사람의 이력·보고서·요청 id 를 넣어도 찾지 못하게 하기 위해서다.
권한 판단은 하지 않는다 (history_service 가 한다).
"""

import json

from core.database import get_connection

_LOG_COLUMNS = "id, created_at, action, target_type, target_id, query, filters, doc_ids, result_count, is_blocked, block_reason"
_REPORT_COLUMNS = "id, title, template, params, content_md, footnotes, exec_summary_md, doc_ids, max_access_level, created_at"
# PyMySQL 은 JSON 컬럼을 문자열로 돌려주므로 읽을 때 파싱한다.
_JSON_COLUMNS = ("filters", "doc_ids", "params", "footnotes")


def _decode(row: dict | None) -> dict | None:
    """행의 JSON 컬럼 문자열을 파이썬 값으로 바꾼다."""
    if row is None:
        return None
    for column in _JSON_COLUMNS:
        if isinstance(row.get(column), (str, bytes)):
            row[column] = json.loads(row[column])
    return row


def list_user_logs(user_id: int, actions: list[str], limit: int) -> list[dict]:
    """M-04 본인의 감사 로그 중 actions 에 해당하는 행을 최신순으로 limit 건 읽는다."""
    if not actions:
        return []
    placeholders = ", ".join(["%s"] * len(actions))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_LOG_COLUMNS} FROM audit_logs "
            f"WHERE user_id = %s AND action IN ({placeholders}) "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            [user_id, *actions, limit],
        )
        return [_decode(row) for row in cur.fetchall()]


def get_user_log(user_id: int, log_id: int, actions: list[str]) -> dict | None:
    """M-04 본인의 감사 로그 1건. 다른 사람 로그이거나 actions 밖이면 None."""
    if not actions:
        return None
    placeholders = ", ".join(["%s"] * len(actions))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_LOG_COLUMNS} FROM audit_logs "
            f"WHERE id = %s AND user_id = %s AND action IN ({placeholders})",
            [log_id, user_id, *actions],
        )
        return _decode(cur.fetchone())


def find_user_report(user_id: int, report_id: int) -> dict | None:
    """M-04 본인이 만든 보고서 1건. 없거나 다른 사람 보고서면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_REPORT_COLUMNS} FROM reports WHERE id = %s AND user_id = %s",
            (report_id, user_id),
        )
        return _decode(cur.fetchone())


def find_report_titles(user_id: int, report_ids: list[int]) -> dict[int, str]:
    """M-04 본인 보고서 id → 제목. 목록에 보고서 제목을 보여 줄 때 쓴다."""
    if not report_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(report_ids))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT id, title FROM reports WHERE user_id = %s AND id IN ({placeholders})",
            [user_id, *report_ids],
        )
        return {row["id"]: row["title"] for row in cur.fetchall()}


def find_documents(doc_ids: list[str]) -> dict[str, dict]:
    """M-04 문서 id → 권한 확인에 필요한 칸(회사·보안 등급·공유 여부)과 제목."""
    if not doc_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(doc_ids))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, company_id, title, access_level, is_group_shared "
            f"FROM documents WHERE doc_id IN ({placeholders})",
            list(doc_ids),
        )
        return {row["doc_id"]: row for row in cur.fetchall()}


def list_access_requests(user_id: int) -> list[dict]:
    """M-04 본인이 신청한 열람 권한 요청을 최신순으로 읽는다. 문서 제목을 함께 가져온다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.doc_id, d.title, r.owner_company_code, r.reason, r.status, "
            "r.review_comment, r.created_at, r.reviewed_at "
            "FROM access_requests r LEFT JOIN documents d ON d.doc_id = r.doc_id "
            "WHERE r.user_id = %s ORDER BY r.created_at DESC, r.id DESC",
            (user_id,),
        )
        return cur.fetchall()
