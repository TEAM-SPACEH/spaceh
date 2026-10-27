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
