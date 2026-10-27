"""S-01 자연어 통합 검색: search_documents().

검색 순서
1) S-03 apply_rbac_filter()로 권한 조건(Chroma where)을 먼저 만든다.
2) 질문을 임베딩(문장을 숫자 벡터로 바꾸는 것)한다. 색인(I-02)과 같은 모델을 써야 비교가 된다.
3) 권한 조건을 건 채로 Chroma에서 질문과 가까운 청크를 찾는다.
   권한 밖 청크는 검색 후보에 아예 들어오지 않는다 (사후 필터 아님).
"""

from langchain_openai import OpenAIEmbeddings

from app.permissions.services.permission_service import apply_rbac_filter
from app.search.repositories.chunk_repository import query_chunks
from core import config


def search_documents(query: str, filters: dict | None, user: dict) -> list[dict]:
    """S-01 3사 문서를 권한 조건에 따라 통합 검색하고 관련도 순으로 반환한다.

    query: 사용자가 입력한 자연어 검색어
    filters: S-02 apply_metadata_filters()가 만든 Chroma where 조각. 없으면 None 또는 {}
    user: 로그인 사용자. {"id": 3, "role": "employee", "company_id": "MVX"} 모양
    반환: 관련도 높은 순 청크 목록
        [{"chunk_id", "doc_id", "text", "score", "metadata"}, ...]
        score는 0~1, 클수록 질문과 가깝다. metadata는 data-model §4 필드 그대로.
    오류: 로그인 정보가 없거나 잘못되면 PermissionError
    """
    # 권한 확인을 검색어 검사보다 먼저 해서, 잘못된 사용자는 어떤 경우에도 통과하지 못하게 한다.
    where = apply_rbac_filter(user, filters)

    query = (query or "").strip()
    if not query:
        return []

    chunks = query_chunks(_embed_query(query), where, config.SEARCH_TOP_K)
    results = [
        {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["metadata"].get("doc_id", ""),
            "text": chunk["text"],
            # 거리(작을수록 가까움)를 점수(클수록 가까움)로 바꾼다.
            # 1/(1+거리)는 거리 방식(l2·cosine)과 관계없이 순서를 그대로 지킨다.
            "score": 1 / (1 + chunk["distance"]),
            "metadata": chunk["metadata"],
        }
        for chunk in chunks
    ]
    return sorted(results, key=lambda result: result["score"], reverse=True)


def _embed_query(query: str) -> list[float]:
    """검색어를 색인(I-02)과 같은 임베딩 모델로 벡터로 바꾼다."""
    embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL, api_key=config.OPENAI_API_KEY)
    return embeddings.embed_query(query)


def apply_metadata_filters(filters: dict) -> dict:
    """S-02 기업·문서 유형·기간 선택값을 Chroma where 조건(dict)으로 바꿔 돌려준다.

    "where 조건"이란 검색 DB(Chroma)에게 "이런 문서만 보라"고 알려 주는 필터다.
    검색을 하기 '전에' 이 조건을 걸어 미리 거른다(결과를 받은 뒤 거르지 않는다).

    입력 filters — render_search_filters()가 돌려준 모양:
        {
            "companies": ["HRI", "MVX"],   # 고른 회사 코드
            "doc_types": ["report"],       # 고른 문서 유형 코드
            "date_from": 20250101,         # 시작일(YYYYMMDD 정수) 또는 None
            "date_to": 20251231,           # 종료일(YYYYMMDD 정수) 또는 None
        }

    반환 — Chroma where 조각(dict):
        - 조건이 없으면 빈 dict {} (필터를 걸지 않음)
        - 한 필드의 값이 1개면 동등 비교({"company_id": "HRI"}), 여러 개면 $in을 쓴다.
        - 조건이 1개면 그 조건을 그대로, 2개 이상이면 {"$and": [...]}로 묶는다.
        - 이 조각은 S-03 권한 필터와 '바깥에서' 다시 $and로 합쳐진다.

    오류:
        시작일(date_from)이 종료일(date_to)보다 늦으면 ValueError를 던진다.
    """
    filters = filters or {}
    conditions: list[dict] = []

    # 1) 기업: 1개면 동등 비교, 여러 개면 $in(목록 중 하나)
    companies = _as_list(filters.get("companies"))
    if companies:
        conditions.append(_match_any("company_id", companies))

    # 2) 문서 유형: 1개면 동등 비교, 여러 개면 $in
    doc_types = _as_list(filters.get("doc_types"))
    if doc_types:
        conditions.append(_match_any("doc_type", doc_types))

    # 3) 기간: 시작일 이상(>=), 종료일 이하(<=). 날짜는 YYYYMMDD 정수로 비교한다.
    #    Chroma는 한 필드에 연산자 하나만 받으므로 시작·종료를 각각 조건으로 넣는다.
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    # 시작일이 종료일보다 늦으면 아무 문서도 못 찾으니, 잘못된 입력으로 보고 바로 알린다.
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError(f"시작일({date_from})이 종료일({date_to})보다 늦습니다.")
    if date_from is not None:
        conditions.append({"published_date": {"$gte": date_from}})
    if date_to is not None:
        conditions.append({"published_date": {"$lte": date_to}})

    # 조건 개수에 따라 돌려주는 모양을 맞춘다.
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _match_any(field: str, values: list) -> dict:
    """한 필드 조건을 만든다. 값이 1개면 동등 비교, 여러 개면 $in(목록 중 하나)."""
    if len(values) == 1:
        return {field: values[0]}
    return {field: {"$in": values}}


def _as_list(value) -> list:
    """필터 값을 목록으로 맞춘다. 문자열 하나면 한 항목짜리 목록으로, 빈 값이면 빈 목록으로.

    문자열은 list()로 풀면 글자 단위로 쪼개지므로("HRI" → ["H","R","I"]) 따로 감싼다.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)
