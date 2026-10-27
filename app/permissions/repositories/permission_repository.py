"""S-03 승인 내역 조회."""

from core.database import get_connection


def get_approved_doc_ids(user_id: int) -> list[str]:
    """S-03 사용자가 열람 승인(A-05)을 받은 문서의 doc_id 목록을 반환한다."""
    # access_grants는 같은 문서가 여러 번 승인될 수 있어 DISTINCT로 한 번씩만 돌려준다.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT doc_id FROM access_grants WHERE user_id = %s",
            (user_id,),
        )
        return [row["doc_id"] for row in cur.fetchall()]
