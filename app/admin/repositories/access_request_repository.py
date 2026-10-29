"""A-05 열람 요청 조회와 승인·반려 트랜잭션."""

from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime

from pymysql.cursors import DictCursor

from core.database import get_connection


@contextmanager
def review_transaction() -> Iterator[DictCursor]:
    """A-05 권한 부여와 요청 상태 변경을 같은 트랜잭션으로 묶는다."""
    with get_connection() as conn, conn.cursor() as cursor:
        yield cursor


def find_reviewer(cursor: DictCursor, user_id: int) -> dict | None:
    """A-05 처리 중 역할 변경을 막도록 활성 사용자 행을 잠근다."""
    cursor.execute(
        "SELECT id, role, company_id FROM users "
        "WHERE id = %s AND is_active = 1 FOR UPDATE", (user_id,),
    )
    return cursor.fetchone()


def find_request(cursor: DictCursor, request_id: int) -> dict | None:
    """A-05 요청과 현재 문서 소유 회사를 잠금 조회한다."""
    cursor.execute(
        "SELECT r.id, r.user_id, r.doc_id, r.status, d.company_id "
        "FROM access_requests r JOIN documents d ON d.doc_id = r.doc_id "
        "WHERE r.id = %s FOR UPDATE", (request_id,),
    )
    return cursor.fetchone()


def insert_grant(cursor: DictCursor, request: dict, reviewer_id: int) -> None:
    """A-05 잠근 요청을 근거로 문서 단위 열람 권한을 저장한다."""
    cursor.execute(
        "INSERT INTO access_grants (user_id, doc_id, request_id, granted_by) "
        "VALUES (%s, %s, %s, %s)",
        (request["user_id"], request["doc_id"], request["id"], reviewer_id),
    )


def save_review(cursor: DictCursor, request_id: int, decision: str,
                reviewer_id: int, reason: str | None, reviewed_at: datetime) -> None:
    """A-05 잠근 대기 요청의 처리 상태·관리자·사유·시각을 저장한다."""
    cursor.execute(
        "UPDATE access_requests SET status = %s, reviewer_id = %s, "
        "review_comment = %s, reviewed_at = %s WHERE id = %s AND status = 'pending'",
        (decision, reviewer_id, reason, reviewed_at, request_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("이미 처리되었거나 삭제된 요청입니다.")


def list_requests(company_id: str | None, status: str | None,
                  limit: int, offset: int) -> tuple[list[dict], int]:
    """A-05 현재 문서 소유 회사와 상태를 검색 전에 제한해 페이지 조회한다."""
    params = (company_id, company_id, status, status)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM access_requests r "
            "JOIN documents d ON d.doc_id = r.doc_id JOIN users u ON u.id = r.user_id "
            "WHERE (%s IS NULL OR d.company_id = %s) AND (%s IS NULL OR r.status = %s)",
            params,
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT r.id, r.user_id, r.doc_id, r.reason, r.status, "
            "r.review_comment, r.created_at, r.reviewed_at, d.title, "
            "d.company_id, u.name AS requester_name, u.employee_no "
            "FROM access_requests r JOIN documents d ON d.doc_id = r.doc_id "
            "JOIN users u ON u.id = r.user_id "
            "WHERE (%s IS NULL OR d.company_id = %s) AND (%s IS NULL OR r.status = %s) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s",
            (*params, limit, offset),
        )
        return list(cursor.fetchall()), total
