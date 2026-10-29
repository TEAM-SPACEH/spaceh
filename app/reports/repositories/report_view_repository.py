"""R-03 보고서 보기 화면용 조회: 보고서 만든 시각과 각주 문서의 출처 종류(내부·DART)."""

from datetime import datetime

from core.database import get_connection


def find_created_at(report_id: int, user_id: int) -> datetime | None:
    """본인 보고서의 만든 시각. 없거나 본인 것이 아니면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT created_at FROM reports WHERE id = %s AND user_id = %s", (report_id, user_id))
        row = cur.fetchone()
    return row["created_at"] if row else None


def find_source_types(doc_ids: list[str]) -> dict[str, str]:
    """문서 ID별 출처 종류('internal' / 'dart'). 지워진 문서는 결과에 없다."""
    if not doc_ids:
        return {}
    # 자리 표시자(%s)만 목록 길이만큼 만들고, 값은 바인딩으로 넘긴다.
    placeholders = ", ".join(["%s"] * len(doc_ids))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT doc_id, source_type FROM documents WHERE doc_id IN ({placeholders})", tuple(doc_ids))
        rows = cur.fetchall()
    return {row["doc_id"]: row["source_type"] for row in rows}
