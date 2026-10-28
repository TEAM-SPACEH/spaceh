"""S-03 승인 내역 조회, M-03 열람 권한 요청 저장."""

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


# 아래 함수들은 '데이터베이스에서 읽고 쓰는 일'만 한다 (판단은 서비스가 함).
# %s는 값이 들어갈 '빈칸'이다. 값을 문자열로 직접 이어 붙이지 않고 빈칸으로 넘겨야
# 안전하다(해킹 수법인 SQL 주입을 막아 준다).


def find_user(user_id: int) -> dict | None:
    """M-03 사원 한 명의 정보(번호·역할·소속 회사)를 데이터베이스에서 찾아온다. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        # users 표에서 id가 user_id와 같은 한 줄을 고른다.
        cur.execute(
            "SELECT id, role, company_id FROM users WHERE id = %s",
            (user_id,),
        )
        return cur.fetchone()  # 한 줄(dict) 또는 없으면 None


def find_document(doc_id: str) -> dict | None:
    """M-03 문서 한 개의 정보(이름표·소유 회사·보안 등급·공유 여부)를 찾아온다. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        # documents 표에서 이름표(doc_id)가 같은 한 줄을 고른다.
        cur.execute(
            "SELECT doc_id, company_id, access_level, is_group_shared "
            "FROM documents WHERE doc_id = %s",
            (doc_id,),
        )
        return cur.fetchone()


def has_pending_request(user_id: int, doc_id: str) -> bool:
    """M-03 이 사람이 이 문서에 대해 '아직 처리 안 된(pending) 요청'을 이미 냈는지 True/False로 알려준다."""
    with get_connection() as conn, conn.cursor() as cur:
        # 조건에 맞는 줄이 하나라도 있으면 되므로, 찾자마자 1줄만(LIMIT 1) 가져온다.
        cur.execute(
            "SELECT 1 FROM access_requests "
            "WHERE user_id = %s AND doc_id = %s AND status = %s LIMIT 1",
            (user_id, doc_id, "pending"),
        )
        # 가져온 줄이 있으면 요청이 있다는 뜻(True), 없으면 None → False.
        return cur.fetchone() is not None


def insert_access_request(user_id: int, doc_id: str, owner_company_code: str, reason: str) -> bool:
    """M-03 열람 요청 1건을 '대기 중' 상태로 새로 저장한다. 잘 저장되면 True.

    status(처리 상태)는 적지 않는다 — 표에서 기본값이 'pending'(대기 중)으로 자동으로 들어간다.
    """
    with get_connection() as conn, conn.cursor() as cur:
        # access_requests 표에 새 줄 하나를 넣는다(누가·어떤 문서·어느 회사가 처리·사유).
        cur.execute(
            "INSERT INTO access_requests (user_id, doc_id, owner_company_code, reason) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, doc_id, owner_company_code, reason),
        )
        # rowcount = 방금 바뀐(들어간) 줄 수. 1이면 한 줄이 잘 들어갔다는 뜻.
        return cur.rowcount == 1
