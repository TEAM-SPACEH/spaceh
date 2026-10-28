"""S-01 자연어 통합 검색: search_documents(), S-06 하이브리드 검색: hybrid_search().

검색 순서
1) S-03 apply_rbac_filter()로 권한 조건(Chroma where)을 먼저 만든다.
2) 질문을 임베딩(문장을 숫자 벡터로 바꾸는 것)한다. 색인(I-02)과 같은 모델을 써야 비교가 된다.
3) 권한 조건을 건 채로 Chroma에서 질문과 가까운 청크를 찾는다.
   권한 밖 청크는 검색 후보에 아예 들어오지 않는다 (사후 필터 아님).

S-06은 3)의 벡터 검색에 BM25 키워드 검색을 더한다. BM25 인덱스도 같은 권한 조건을
통과한 청크만으로 만든다 (docs/architecture/overview.md §2.3).
"""

import re

from langchain_openai import OpenAIEmbeddings
from rank_bm25 import BM25L

from app.permissions.services.permission_service import apply_rbac_filter
from app.search.repositories.chunk_repository import get_chunks, query_chunks
from core import config

# 하이브리드 검색에서 결합 전에 각 검색이 가져올 후보 수 = 최종 결과 수(SEARCH_TOP_K) × 이 값.
# 최종 수만큼만 가져오면 양쪽에서 11위인 청크처럼 합치면 위로 올라올 청크가 결합 전에 잘린다.
_HYBRID_CANDIDATE_FACTOR = 3

# 영문·숫자 묶음(모델명 "WBST-500", "HD2000" 등)과 한글 묶음을 토큰으로 뽑는다.
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*|[가-힣]+")


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

    return vector_search(query, where)


def hybrid_search(query: str, filters: dict | None, user: dict) -> list[dict]:
    """S-06 BM25 및 벡터 검색 결과를 결합하고 중복 제거 후 관련도 순으로 정렬한다.

    입력·반환·오류는 search_documents()와 같다. score는 0~1로, 두 검색 모두에서 1등이면 1이다.
    """
    where = apply_rbac_filter(user, filters)

    query = (query or "").strip()
    if not query:
        return []

    # BM25 점수와 벡터 점수는 범위가 달라 그대로 더할 수 없다.
    # 그래서 각 검색의 '순위'만 보고 1/(k+순위)를 더한다 (RRF, Reciprocal Rank Fusion).
    # 같은 청크가 양쪽에 나오면 chunk_id 하나로 합쳐지고 점수가 더해진다.
    # BM25 결과를 먼저 넣는다. 점수가 같으면 먼저 넣은 쪽이 앞에 남으므로(안정 정렬),
    # BM25에서만 1등인 모델명 청크가 벡터에서만 1등인 청크보다 앞선다.
    rrf_k = config.HYBRID_RRF_K
    candidate_k = config.SEARCH_TOP_K * _HYBRID_CANDIDATE_FACTOR
    merged: dict[str, dict] = {}
    for results in (bm25_search(query, where, candidate_k), vector_search(query, where, candidate_k)):
        for rank, result in enumerate(results, start=1):
            entry = merged.setdefault(result["chunk_id"], {**result, "score": 0.0})
            entry["score"] += 1 / (rrf_k + rank)

    # 양쪽 모두 1등일 때의 점수로 나눠 0~1로 맞춘다 (화면의 관련도 표시와 같은 범위).
    best = 2 / (rrf_k + 1)
    for entry in merged.values():
        entry["score"] /= best
    ranked = sorted(merged.values(), key=lambda result: result["score"], reverse=True)
    return ranked[: config.SEARCH_TOP_K]


def vector_search(query: str, filters: dict | None, top_k: int | None = None) -> list[dict]:
    """S-06 권한이 허용된 문서 청크를 대상으로 임베딩 기반 의미 유사도 검색을 한다.

    filters: apply_rbac_filter()가 만든 권한 포함 where. 권한 조건이 없는 where를 넘기지 않는다.
    top_k: 가져올 청크 수. 없으면 SEARCH_TOP_K. hybrid_search()는 결합용으로 더 많이 가져온다.
    반환 모양은 search_documents()와 같다.
    명세상 user를 받지 않아 권한을 직접 확인하지 않는다. 다른 기능은 이 함수 대신 hybrid_search()를 부른다.
    """
    chunks = query_chunks(_embed_query(query), filters, top_k or config.SEARCH_TOP_K)
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


def bm25_search(query: str, filters: dict | None, top_k: int | None = None) -> list[dict]:
    """S-06 권한이 허용된 문서에서 키워드·모델명·고유명사 기반으로 검색한다.

    filters: apply_rbac_filter()가 만든 권한 포함 where. 이 조건을 통과한 청크만으로 인덱스를 만든다.
    top_k: 돌려줄 청크 수. 없으면 SEARCH_TOP_K. hybrid_search()는 결합용으로 더 많이 가져온다.
    반환 모양은 search_documents()와 같다. score는 BM25 점수(클수록 관련, 상한 없음).
    검색어 토큰이 하나도 들어 있지 않은 청크는 돌려주지 않는다.
    명세상 user를 받지 않아 권한을 직접 확인하지 않는다. 다른 기능은 이 함수 대신 hybrid_search()를 부른다.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    chunks = get_chunks(filters)
    if not chunks:
        return []

    # 검색할 때마다 허용 청크로 인덱스를 새로 만든다. 사용자마다 허용 범위가 달라 미리 만들어 둘 수 없다.
    corpus = [_tokenize(chunk["text"]) for chunk in chunks]
    # 토큰이 하나도 없으면 rank_bm25가 0으로 나누다 실패한다. 벡터 검색 결과는 살리도록 빈 목록으로 끝낸다.
    if not any(corpus):
        return []
    # BM25Okapi는 청크가 적으면(필터를 좁게 건 경우) 단어 희귀도(IDF)가 0·음수가 되어
    # 검색어가 더 많이 든 청크가 오히려 아래로 간다. BM25L은 IDF가 항상 양수라 순위가 뒤집히지 않는다.
    scores = BM25L(corpus).get_scores(query_tokens)

    query_token_set = set(query_tokens)
    results = [
        {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["metadata"].get("doc_id", ""),
            "text": chunk["text"],
            "score": float(score),
            "metadata": chunk["metadata"],
        }
        for chunk, tokens, score in zip(chunks, corpus, scores)
        if query_token_set.intersection(tokens)
    ]
    results.sort(key=lambda result: result["score"], reverse=True)
    return results[: top_k or config.SEARCH_TOP_K]


def _tokenize(text: str) -> list[str]:
    """BM25용 토큰 목록을 만든다. 형태소 분석기 없이 쓰는 단순 방식이다.

    - 영문·숫자 묶음은 소문자로 통째로 쓴다. 모델명이 쪼개지면 키워드 검색 장점이 사라진다.
    - 한글 묶음은 두 글자씩 겹쳐 자른다(바이그램). "엘리베이터의"와 "엘리베이터"처럼
      조사가 붙어도 "엘리", "리베" 같은 조각이 겹쳐 서로 찾을 수 있다.
    """
    tokens: list[str] = []
    for word in _TOKEN_PATTERN.findall((text or "").lower()):
        if word[0] >= "가" and len(word) >= 2:
            tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


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
