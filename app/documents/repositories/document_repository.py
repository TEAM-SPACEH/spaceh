"""S-05 원문 보기용 문서 정보 조회."""

# repositories 파일 = DB에서 읽고 쓰기만 하는 곳이에요. 권한 판단 같은 업무 판단은 하지 않아요. (팀 규칙)

from core.database import get_connection  # 팀 규칙: DB 연결은 반드시 이 함수로만 열어요


def find_by_id(doc_id: str) -> dict | None:
    """S-05 doc_id로 documents 행 1건을 조회한다. 없으면 None."""
    # SELECT * 대신 필요한 칸만 적었어요.
    # 원문 보기에 필요 없는 값(content_hash, 업로드한 사람 등)까지 화면 쪽으로 흘러가지 않게 하려고요.
    # 값은 반드시 %s 자리로 넘겨요. 문자열을 이어 붙여 SQL을 만들면 SQL 인젝션 공격에 뚫려요. (팀 규칙)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, company_id, title, file_name, file_format, source_type, "
            "source_url, doc_no, access_level, is_group_shared, file_path, page_count "
            "FROM documents WHERE doc_id = %s",
            (doc_id,),
        )
        # fetchone(): 결과 1줄을 딕셔너리로 돌려줘요. 없으면 None이에요.
        return cur.fetchone()
