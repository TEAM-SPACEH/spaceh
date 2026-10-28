"""A-01 회사 조회와 중복 검사·문서 등록·색인 상태 저장."""

from core.database import get_connection


def find_active_admin(user_id: int) -> dict | None:
    """A-01 세션 생성 후 변경된 역할·활성 상태도 DB에서 확인한다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, role, company_id FROM users "
            "WHERE id = %s AND is_active = 1", (user_id,),
        )
        return cur.fetchone()


def list_active_companies() -> list[dict]:
    """A-01 고정 회사 목록 대신 등록된 활성 회사를 반환한다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT company_id, name FROM companies WHERE is_active = 1 ORDER BY name")
        return cur.fetchall()


def find_duplicate(company_id: str, content_hash: str) -> dict | None:
    """A-01 같은 회사의 동일 원본만 조회하고 경로·본문은 반환하지 않는다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, title, index_status FROM documents "
            "WHERE company_id = %s AND content_hash = %s LIMIT 1",
            (company_id, content_hash),
        )
        return cur.fetchone()


def insert_document(document: dict) -> dict | None:
    """A-01 회사 행 잠금 안에서 중복을 재확인하고 pending 문서를 등록한다."""
    with get_connection() as conn, conn.cursor() as cur:
        # 동일 기업의 동시 등록을 직렬화하되 외부 API 호출까지 잠금을 유지하지 않는다.
        cur.execute(
            "SELECT company_id FROM companies "
            "WHERE company_id = %s AND is_active = 1 FOR UPDATE",
            (document["company_id"],),
        )
        if cur.fetchone() is None:
            raise ValueError("활성 회사가 아닙니다.")
        cur.execute(
            "SELECT doc_id, title, index_status FROM documents "
            "WHERE company_id = %s AND content_hash = %s LIMIT 1 FOR UPDATE",
            (document["company_id"], document["content_hash"]),
        )
        duplicate = cur.fetchone()
        if duplicate:
            return duplicate
        cur.execute(
            "INSERT INTO documents "
            "(doc_id, company_id, doc_type, title, file_name, file_format, "
            "published_date, access_level, is_group_shared, is_mock, file_path, "
            "content_hash, uploaded_by, created_at, index_status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            tuple(document[key] for key in (
                "doc_id", "company_id", "doc_type", "title", "file_name", "file_format",
                "published_date", "access_level", "is_group_shared", "is_mock",
                "file_path", "content_hash", "uploaded_by", "created_at", "index_status",
            )),
        )
        return None


def update_index_status(doc_id: str, status: str, chunk_count: int, error_message: str) -> None:
    """A-01 파이프라인의 완료·실패 결과를 문서 행에 반영한다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET index_status = %s, chunk_count = %s, "
            "error_message = %s WHERE doc_id = %s",
            (status, chunk_count, error_message, doc_id),
        )
