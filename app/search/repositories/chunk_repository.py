"""S-01 Chroma 청크 조회."""

import logging

from chromadb.errors import NotFoundError

from core import config
from core.chroma import open_chroma_client

logger = logging.getLogger(__name__)


def query_chunks(query_embedding: list[float], where: dict | None, n_results: int) -> list[dict]:
    """S-01 where 조건을 건 채로 질문 벡터와 가까운 청크를 가까운 순으로 돌려준다.

    반환: [{"chunk_id", "text", "metadata", "distance"}, ...]  distance가 작을수록 가깝다.
    """
    # 검색이 끝나거나 예외가 나도 닫는다 (core.chroma: 열고 닫기를 잠금으로 직렬화, Windows 파일 잠금 해제).
    with open_chroma_client() as client:
        try:
            collection = client.get_collection(config.CHROMA_COLLECTION)
        except NotFoundError:
            # 여기서 컬렉션을 만들면 I-02가 정할 거리 방식(cosine 등)과 어긋날 수 있어 만들지 않는다.
            logger.warning("Chroma 컬렉션 '%s'이 아직 없습니다. 색인(I-02) 후 검색할 수 있습니다.", config.CHROMA_COLLECTION)
            return []

        # Chroma는 빈 where({})를 오류로 처리하므로 None으로 넘긴다.
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
    # 질문을 1개만 보냈으므로 결과 목록의 첫 번째 묶음만 쓴다.
    return [
        {"chunk_id": chunk_id, "text": text, "metadata": metadata, "distance": distance}
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]
