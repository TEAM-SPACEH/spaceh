"""S-05 원문 보기용 문서 정보 조회."""

# repositories 파일 = DB에서 읽고 쓰기만 하는 곳이에요. 권한 판단 같은 업무 판단은 하지 않아요. (팀 규칙)

from core.database import get_connection  # 팀 규칙: DB 연결은 반드시 이 함수로만 열어요


def find_by_id(doc_id: str) -> dict | None:
    """S-05 doc_id로 documents 행 1건을 조회한다. 없으면 None."""
    # SELECT * 대신 필요한 칸만 적었어요.
    # 원문 보기에 필요 없는 값(content_hash, 업로드한 사람 등)까지 화면 쪽으로 흘러가지 않게 하려고요.
    # 값은 반드시 %s 자리로 넘겨요. 문자열을 이어 붙여 SQL을 만들면 SQL 인젝션 공격에 뚫려요. (팀 규칙)
    with get_connection() as conn, conn.cursor() as cur:
        # 뷰어 오른쪽 "문서 정보" 칸(소유 회사·작성일·개인정보 가림·색인)에 쓸 값도 함께 읽어요.
        cur.execute(
            "SELECT d.doc_id, d.company_id, c.name AS company_name, d.title, d.file_name, d.file_format, "
            "d.source_type, d.source_url, d.doc_no, d.access_level, d.is_group_shared, d.file_path, "
            "d.page_count, d.published_date, d.pii_masked_count, d.chunk_count, d.updated_at "
            "FROM documents d LEFT JOIN companies c ON c.company_id = d.company_id "
            "WHERE d.doc_id = %s",
            (doc_id,),
        )
        # fetchone(): 결과 1줄을 딕셔너리로 돌려줘요. 없으면 None이에요.
        return cur.fetchone()
