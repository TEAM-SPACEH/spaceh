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
# A-02 목록에 필요한 컬럼만 가져온다. 파일 경로·해시처럼 화면에 필요 없는 값은 뺀다.
# (repositories 계층: SQL 실행만 한다. 누가 볼 수 있는지는 services 계층이 정하고, 여기서는 받은 값을 그대로 쓴다.)
_A02_LIST_COLUMNS = (
    "doc_id, company_id, title, file_name, file_format, doc_type, source_type, access_level, "
    "is_group_shared, chunk_count, index_status, error_message, created_at, updated_at"
)
# 멈춘 작업인지 DB 시각으로 판단한다 (앱과 DB의 시간대가 달라도 어긋나지 않는다).
# is_stale = 1 이면 "마지막 갱신이 N분보다 오래됨"이다. 색인 중인데 이렇게 오래 멈춰 있으면 서버가 도중에 꺼진 것으로 본다.
# 비교는 파이썬이 아니라 MySQL이 한다. updated_at 은 MySQL 시계로 찍히므로, 앱과 DB의 시간대가 달라도 어긋나지 않는다.
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
    # WHERE 조건을 "조각"으로 모았다가 AND 로 잇는다. 조각 문자열은 모두 코드에 고정된 글자이고,
    # 사용자가 고른 값은 %s 자리에 params 로만 넘긴다 (SQL 주입 방지: 입력값이 SQL 문장으로 해석되지 않고 값으로만 취급된다).
    conditions: list[str] = []
    params: list = []
    # 조각은 모두 코드에 고정된 글자이고, 입력값은 %s 자리에 params로만 넘긴다.
    # 컬럼 이름 네 개는 코드에 박혀 있는 값이라 f-string 으로 SQL 에 넣어도 안전하다 (사용자 입력이 아니다).
    # 값이 빈 문자열이면 "전체"라는 뜻이라 조건을 걸지 않는다.
    for column, value in (("company_id", company_id), ("doc_type", doc_type),
                          ("access_level", access_level), ("index_status", index_status)):
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)
    # 제목이나 파일명에 검색어가 들어 있는 문서. OR 조건은 괄호로 묶어, 뒤에 AND 로 붙는 다른 조건과 섞이지 않게 한다.
    # LIKE 의 앞뒤 % 는 "아무 글자나 와도 됨"이라는 뜻이고, 사용자가 입력한 % _ 는 _escape_like 로 글자 그대로 찾게 막는다.
    if keyword:
        conditions.append("(title LIKE %s OR file_name LIKE %s)")
        pattern = f"%{_escape_like(keyword)}%"
        params.extend([pattern, pattern])
    # 조건이 하나도 없으면(전체 조회) 항상 참인 "1 = 1" 을 써서 WHERE 문법이 깨지지 않게 한다.
    where = " AND ".join(conditions) or "1 = 1"
    with get_connection() as conn, conn.cursor() as cur:
        # 전체 건수(페이지 수 계산용)와 한 페이지 분량을 같은 연결에서 읽는다.
        # 정렬은 최신순이고, 같은 시각이면 doc_id 로 순서를 고정해 페이지를 넘길 때 문서가 겹치거나 빠지지 않게 한다.
        # select 의 %s(stale_minutes)가 WHERE 의 %s 보다 앞에 있어서 params 맨 앞에 stale_minutes 를 둔다.
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
            # 회사명은 companies 에서 JOIN 으로 가져온다 (재색인 때 Chroma 메타데이터의 company_name 에 필요).
            # file_path 는 화면으로 내보내지 않고 서비스가 파일을 찾을 때만 쓴다.
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
    선점하면 바꾸기 전 값({"index_status", "chunk_count", "error_message", "updated_at"})을, 못 하면 None을 반환한다.
    updated_at 은 작업이 실패했을 때 restore_claimed_document 가 선점 전 값으로 되돌리려고 함께 돌려준다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT index_status, chunk_count, error_message, updated_at, "
            "(updated_at < NOW() - INTERVAL %s MINUTE) AS is_stale "
            "FROM documents WHERE doc_id = %s FOR UPDATE",
            (stale_minutes, doc_id),
        )
        # 위 SELECT ... FOR UPDATE 는 이 행을 "잠근" 채 읽는다. 다른 요청이 같은 행을 바꾸려 하면 이 트랜잭션이 끝날 때까지 기다린다.
        # 그래서 "상태 확인 → 처리 중으로 변경" 사이에 다른 요청이 끼어들 수 없다 (서버가 여러 개여도 DB가 막아 준다).
        row = cur.fetchone()
        # 문서가 없으면 선점할 수 없다 (이미 삭제됨). 서비스가 먼저 조회해서 안내 문구를 정한다.
        if row is None:
            return None
        # 끝난 상태(완료·실패)가 아니고 멈춘 것도 아니면, 지금 다른 요청이 처리 중이라는 뜻이므로 선점하지 않는다.
        if row["index_status"] not in ("done", "failed") and not row["is_stale"]:
            return None
        # "처리 중" 표시를 해 두면 이 작업이 끝날 때까지 다른 삭제·재색인·공유 변경(A-03)이 거부된다.
        # with 블록을 정상으로 빠져나갈 때 commit 되고 잠금이 풀린다. 바꾸기 전 값은 호출한 쪽이 실패 시 되돌리려고 돌려받는다.
        # updated_at 을 NOW() 로 직접 적는다. 멈춘 'indexing' 을 다시 선점하면 index_status 값이 그대로라
        # ON UPDATE CURRENT_TIMESTAMP 가 동작하지 않아, 선점한 뒤에도 계속 "멈춘 작업"으로 보이기 때문이다.
        cur.execute(
            "UPDATE documents SET index_status = 'indexing', updated_at = NOW() WHERE doc_id = %s", (doc_id,)
        )
        return {"index_status": row["index_status"], "chunk_count": row["chunk_count"],
                "error_message": row["error_message"], "updated_at": row["updated_at"]}


def restore_claimed_document(doc_id: str, previous: dict) -> None:
    """A-02 선점해 둔 문서를 선점하기 전 값(claim_document 가 돌려준 previous)으로 되돌린다.

    상태·청크 수·오류 문구와 함께 updated_at 도 되돌린다. updated_at 을 적지 않으면 선점 때 찍힌 현재 시각이 남아,
    멈춘 작업(indexing)이었던 문서가 실패 뒤에도 STALE_MINUTES 동안 다시 삭제·재색인할 수 없게 된다.
    updated_at 을 직접 적으면 ON UPDATE CURRENT_TIMESTAMP 가 그 값을 덮어쓰지 않는다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET index_status = %s, chunk_count = %s, error_message = %s, updated_at = %s "
            "WHERE doc_id = %s",
            (previous["index_status"], previous["chunk_count"], previous["error_message"] or "",
             previous["updated_at"], doc_id),
        )


def delete_document_row(doc_id: str) -> bool:
    """A-02 문서 행을 삭제한다. 열람 요청·승인은 FK의 ON DELETE CASCADE로 함께 지워진다. 지웠으면 True."""
    with get_connection() as conn, conn.cursor() as cur:
        # access_requests·access_grants 는 FK 의 ON DELETE CASCADE 라서 이 문서의 열람 요청·승인 기록도 같이 지워진다.
        # rowcount 는 실제로 지운 행 수다. 그 사이 다른 곳에서 이미 지웠다면 0 이 된다.
        cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
        return cur.rowcount == 1


# ---------------------------------------------------------------------------
# A-02·A-03 문서 화면(UI v4) 요약·상세. 이 구역 아래는 관리자 문서 화면 전용이다.
# ---------------------------------------------------------------------------

# 최근 몇 일의 추가 건수를 막대로 보여 줄지 (오늘 포함)
OVERVIEW_DAYS = 7


def count_document_overview(company_id: str | None) -> dict:
    """A-02 문서 화면 위쪽 카드용 집계를 읽는다. 날짜 계산은 DB 시계(CURDATE·NOW)로 해 앱과 시간대가 달라도 어긋나지 않는다.

    company_id: 이 회사 문서만 센다. None이면 전체 회사 (권한은 services가 정한다)
    반환: {"total", "internal_total", "shared", "failed", "failed_title", "daily"(오래된 날 → 오늘 순 7개),
           "pending_requests", "oldest_pending_hours"}
        shared는 공유 ON 사내 문서 수. failed_title은 가장 최근에 실패한 문서 제목(없으면 빈 문자열).
        oldest_pending_hours는 가장 오래된 대기 열람 요청이 몇 시간 지났는지(대기가 없으면 0).
    """
    # 회사 조건은 (%s IS NULL OR ... = %s) 고정 SQL로 둔다. company_id가 None이면 전체 회사가 된다.
    params = [company_id, company_id]
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(access_level = 'internal'), 0) AS internal_total, "
            "COALESCE(SUM(access_level = 'internal' AND is_group_shared = 1), 0) AS shared, "
            "COALESCE(SUM(index_status = 'failed'), 0) AS failed "
            "FROM documents WHERE (%s IS NULL OR company_id = %s)",
            params,
        )
        counts = cur.fetchone()
        cur.execute(
            "SELECT title FROM documents WHERE (%s IS NULL OR company_id = %s) AND index_status = 'failed' "
            "ORDER BY updated_at DESC, doc_id LIMIT 1",
            params,
        )
        failed = cur.fetchone()
        cur.execute(
            "SELECT DATEDIFF(CURDATE(), DATE(created_at)) AS days_ago, COUNT(*) AS n "
            "FROM documents WHERE (%s IS NULL OR company_id = %s) "
            "AND created_at >= CURDATE() - INTERVAL %s DAY "
            "GROUP BY days_ago",
            [*params, OVERVIEW_DAYS - 1],
        )
        by_day = {int(row["days_ago"]): int(row["n"]) for row in cur.fetchall()}
        # 열람 요청은 문서 소유 회사 기준이다 (A-05 목록과 같은 범위).
        cur.execute(
            "SELECT COUNT(*) AS pending, "
            "COALESCE(TIMESTAMPDIFF(HOUR, MIN(r.created_at), NOW()), 0) AS oldest_hours "
            "FROM access_requests r JOIN documents d ON d.doc_id = r.doc_id "
            "WHERE r.status = 'pending' AND (%s IS NULL OR d.company_id = %s)",
            params,
        )
        pending = cur.fetchone()
    return {
        "total": int(counts["total"]),
        "internal_total": int(counts["internal_total"]),
        "shared": int(counts["shared"]),
        "failed": int(counts["failed"]),
        "failed_title": failed["title"] if failed else "",
        "daily": [by_day.get(days_ago, 0) for days_ago in range(OVERVIEW_DAYS - 1, -1, -1)],
        "pending_requests": int(pending["pending"]),
        "oldest_pending_hours": int(pending["oldest_hours"] or 0),
    }


def find_document_detail(doc_id: str) -> dict | None:
    """A-03 상세 패널용으로 문서의 소유 회사 이름과 올린 사람 이름을 조회한다. 없으면 None.

    올린 사람이 삭제됐거나 기록이 없으면 uploader_name은 None이다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT d.doc_id, d.company_id, c.name AS company_name, d.access_level, d.is_group_shared, "
            "d.created_at, u.name AS uploader_name "
            "FROM documents d JOIN companies c ON c.company_id = d.company_id "
            "LEFT JOIN users u ON u.id = d.uploaded_by WHERE d.doc_id = %s",
            (doc_id,),
        )
        return cur.fetchone()


def count_document_viewers(doc_id: str, company_id: str) -> dict:
    """A-03 "볼 수 있는 사람" 목록 재료: 소유 회사의 사원·관리자 수, 최종 어드민 수, 승인받은 사용자 목록.

    반환: {"employees", "company_admins", "super_admins", "grants": [{"name", "company_id", "granted_at"}]}
        grants는 이 문서의 열람 승인(access_grants)을 받은 활성 사용자를 최근 승인 순으로 담는다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(role = 'employee' AND company_id = %s), 0) AS employees, "
            "COALESCE(SUM(role = 'company_admin' AND company_id = %s), 0) AS company_admins, "
            "COALESCE(SUM(role = 'super_admin'), 0) AS super_admins "
            "FROM users WHERE is_active = 1",
            (company_id, company_id),
        )
        counts = cur.fetchone()
        cur.execute(
            "SELECT u.name, u.company_id, MAX(g.created_at) AS granted_at "
            "FROM access_grants g JOIN users u ON u.id = g.user_id "
            "WHERE g.doc_id = %s AND u.is_active = 1 "
            "GROUP BY u.id, u.name, u.company_id ORDER BY granted_at DESC",
            (doc_id,),
        )
        grants = list(cur.fetchall())
    return {
        "employees": int(counts["employees"]),
        "company_admins": int(counts["company_admins"]),
        "super_admins": int(counts["super_admins"]),
        "grants": grants,
    }
