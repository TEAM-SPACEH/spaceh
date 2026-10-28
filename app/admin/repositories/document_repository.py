"""A-01 회사 조회와 중복 검사·문서 등록·색인 상태 저장."""

from chromadb.errors import NotFoundError

from core import config
from core.chroma import open_chroma_client
from core.database import get_connection


def delete_document_chunks(doc_id: str) -> None:
    """A-01 실패가 확정된 신규 업로드의 청크만 삭제한다."""
    with open_chroma_client() as client:
        try:
            collection = client.get_collection(config.CHROMA_COLLECTION)
        except NotFoundError:
            return
        collection.delete(where={"doc_id": doc_id})


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


# ---------------------------------------------------------------------------
# A-02 문서 목록 조회·삭제·재색인 (이 구역 아래는 A-02 전용이다. 위의 A-01 함수는 바꾸지 않는다)
# ---------------------------------------------------------------------------

# 목록 SELECT 컬럼 (고정 문자열이라 f-string으로 SQL에 넣어도 안전하다).
_A02_LIST_COLUMNS = (
    "doc_id, company_id, title, file_name, file_format, doc_type, source_type, access_level, "
    "is_group_shared, chunk_count, index_status, error_message, created_at, updated_at"
)
# 멈춘 작업인지 DB 시각으로 판단한다 (앱과 DB의 시간대가 달라도 어긋나지 않는다).
_A02_STALE_COLUMN = "(updated_at < NOW() - INTERVAL %s MINUTE) AS is_stale"


def _escape_like(text: str) -> str:
    """A-02 LIKE 패턴의 특수문자(% _ \\)를 글자 그대로 찾도록 이스케이프한다."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_managed_documents(
    company_id: str | None, doc_type: str, access_level: str, index_status: str,
    keyword: str, limit: int, offset: int, stale_minutes: int,
) -> tuple[list[dict], int]:
    """A-02 관리 가능한 문서를 최신순으로 한 페이지 조회한다.

    company_id: 이 회사 문서만. None이면 전체 회사(최종 어드민)
    doc_type·access_level·index_status·keyword: 빈 문자열이면 조건을 걸지 않는다
    stale_minutes: 이 시간 넘게 갱신이 없는 행에 is_stale=1을 붙인다 (멈춘 색인 작업 판단용)
    반환: (행 목록, 조건에 맞는 전체 건수)
    """
    conditions: list[str] = []
    params: list = []
    # 조각은 모두 코드에 고정된 글자이고, 입력값은 %s 자리에 params로만 넘긴다.
    for column, value in (("company_id", company_id), ("doc_type", doc_type),
                          ("access_level", access_level), ("index_status", index_status)):
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)
    if keyword:
        conditions.append("(title LIKE %s OR file_name LIKE %s)")
        pattern = f"%{_escape_like(keyword)}%"
        params.extend([pattern, pattern])
    where = " AND ".join(conditions) or "1 = 1"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM documents WHERE {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT {_A02_LIST_COLUMNS}, {_A02_STALE_COLUMN} FROM documents WHERE {where} "
            "ORDER BY created_at DESC, doc_id LIMIT %s OFFSET %s",
            [stale_minutes, *params, limit, offset],
        )
        return list(cur.fetchall()), total


def get_managed_document(doc_id: str) -> dict | None:
    """A-02 권한 확인·삭제·재색인에 필요한 문서 1건과 회사명을 조회한다. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT d.doc_id, d.company_id, c.name AS company_name, d.doc_type, d.title, "
            "d.file_name, d.file_format, d.source_type, d.source_url, d.published_date, "
            "d.access_level, d.is_group_shared, d.file_path, d.index_status, d.chunk_count, "
            "d.error_message, d.created_at "
            "FROM documents d JOIN companies c ON c.company_id = d.company_id "
            "WHERE d.doc_id = %s",
            (doc_id,),
        )
        return cur.fetchone()


def claim_document(doc_id: str, stale_minutes: int) -> dict | None:
    """A-02 삭제·재색인 작업을 하나만 실행하도록 문서를 "처리 중"(indexing)으로 선점한다.

    선점할 수 있는 상태: 색인 완료(done)·실패(failed), 또는 stale_minutes보다 오래 멈춘 대기(pending)·처리 중(indexing).
    행을 잠근 채 확인하고 바꾸므로 서버가 여러 개여도 같은 문서에 두 작업이 동시에 들어가지 못한다.
    선점하면 바꾸기 전 값({"index_status", "chunk_count", "error_message"})을, 못 하면 None을 반환한다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT index_status, chunk_count, error_message, "
            "(updated_at < NOW() - INTERVAL %s MINUTE) AS is_stale "
            "FROM documents WHERE doc_id = %s FOR UPDATE",
            (stale_minutes, doc_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        if row["index_status"] not in ("done", "failed") and not row["is_stale"]:
            return None
        cur.execute("UPDATE documents SET index_status = 'indexing' WHERE doc_id = %s", (doc_id,))
        return {"index_status": row["index_status"], "chunk_count": row["chunk_count"],
                "error_message": row["error_message"]}


def delete_document_row(doc_id: str) -> bool:
    """A-02 문서 행을 삭제한다. 열람 요청·승인은 FK의 ON DELETE CASCADE로 함께 지워진다. 지웠으면 True."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
        return cur.rowcount == 1
