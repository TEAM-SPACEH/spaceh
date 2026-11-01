"""M-03 요청 후보 조회: documents 테이블에서 제목·메타데이터로만 찾는다(본문 청크는 건드리지 않는다).

요청 후보는 '권한이 없어 요청하면 볼 수 있는' 문서의 제목만 보여 주는 용도다. 권한 밖 문서의
본문을 벡터 검색(Chroma)으로 끌어오면 '벡터 검색 전에 권한을 건다'는 원칙(overview.md §2.3)을
어기게 된다. 그래서 여기서는 본문이 아니라 MySQL documents 테이블의 '제목·메타데이터'만 조회한다.

repositories 파일 = DB에서 읽고 쓰기만 하는 곳. 권한 판단 같은 업무 판단은 서비스가 한다. (팀 규칙)
값은 반드시 %s 자리로 넘긴다. 문자열을 이어 붙여 SQL을 만들면 SQL 인젝션 공격에 뚫린다. (팀 규칙)
"""

from core.database import get_connection  # 팀 규칙: DB 연결은 반드시 이 함수로만 연다


def search_requestable_candidates(
    query: str,
    companies: list[str],
    doc_types: list[str],
    date_from: int | None,
    date_to: int | None,
    limit: int,
) -> list[dict]:
    """제목에 검색어가 들어가고 S-02 필터에 맞는 문서를 최신순으로 돌려준다(본문 미포함).

    - 반환 각 행: {doc_id, title, company_id, company_name, access_level, is_group_shared}
      권한 판정에 필요한 메타데이터만 돌려준다. 본문·파일 경로 등은 돌려주지 않는다.
    - date_from/date_to는 YYYYMMDD 정수(S-02 필터 형식)다. DATE 컬럼과 비교하려고 날짜로 바꾼다.
    - 색인이 끝난(index_status='done') 문서만 본다(실제 검색 대상과 범위를 맞춘다).
    - 제목 LIKE의 와일드카드(%, _)는 글자 그대로 찾도록 이스케이프한다(검색어가 '50%' 등일 때 안전).
    """
    # WHERE 조건을 리스트로 쌓고 마지막에 이어 붙인다. IN 자리표시자(%s)는 값 개수만큼 만든다.
    sql = [
        "SELECT d.doc_id, d.title, d.company_id, c.name AS company_name, "
        "       d.access_level, d.is_group_shared "
        "FROM documents d "
        "LEFT JOIN companies c ON c.company_id = d.company_id "
        "WHERE d.index_status = 'done' "
        "  AND d.title LIKE %s ESCAPE '!' "
    ]
    params: list = [f"%{_escape_like(query)}%"]

    # 기업: 고른 회사만 (여러 개면 IN)
    if companies:
        placeholders = ", ".join(["%s"] * len(companies))
        sql.append(f"AND d.company_id IN ({placeholders}) ")
        params.extend(companies)
    # 문서 유형: 고른 유형만 (여러 개면 IN)
    if doc_types:
        placeholders = ", ".join(["%s"] * len(doc_types))
        sql.append(f"AND d.doc_type IN ({placeholders}) ")
        params.extend(doc_types)
    # 기간: 시작일 이상, 종료일 이하 (YYYYMMDD 정수를 DATE 문자열로 바꿔 비교)
    if date_from is not None:
        sql.append("AND d.published_date >= %s ")
        params.append(_yyyymmdd_to_date(date_from))
    if date_to is not None:
        sql.append("AND d.published_date <= %s ")
        params.append(_yyyymmdd_to_date(date_to))

    # 최신 문서부터, 상한(limit)만큼만 가져온다. doc_id를 2차 정렬로 둬 순서를 고정한다.
    sql.append("ORDER BY d.published_date DESC, d.doc_id LIMIT %s")
    params.append(limit)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("".join(sql), tuple(params))
        return cur.fetchall()


def _escape_like(text: str) -> str:
    """LIKE에서 특수문자로 쓰이는 !, %, _ 를 글자 그대로 찾도록 '!'로 이스케이프한다(ESCAPE '!'와 짝)."""
    text = text or ""
    # '!'를 먼저 바꿔야(이스케이프 문자 자신) %·_에 붙인 '!'가 다시 바뀌지 않는다.
    for ch in ("!", "%", "_"):
        text = text.replace(ch, f"!{ch}")
    return text


def _yyyymmdd_to_date(value: int) -> str:
    """YYYYMMDD 정수를 'YYYY-MM-DD' 문자열로 바꾼다(DATE 컬럼 비교용). 예: 20250102 → '2025-01-02'."""
    return f"{value // 10000:04d}-{value // 100 % 100:02d}-{value % 100:02d}"
