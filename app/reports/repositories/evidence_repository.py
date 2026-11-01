"""R-01 근거 문서 수 미리보기용 Chroma 조회: 본문 없이 메타데이터만 읽는다."""

import logging

from chromadb.errors import NotFoundError

from core import config
from core.chroma import open_chroma_client

logger = logging.getLogger(__name__)


def get_chunk_metadatas(where: dict | None) -> list[dict]:
    """where 조건을 통과한 청크의 메타데이터만 돌려준다. 본문(documents)은 읽지 않는다.

    where: 권한 조건이 들어간 Chroma where 식. 컬렉션이 아직 없으면 빈 목록
    반환: [{"doc_id", "company_id", ...}, ...]  Chroma 메타데이터 그대로
    """
    with open_chroma_client() as client:
        try:
            collection = client.get_collection(config.CHROMA_COLLECTION)
        except NotFoundError:
            logger.warning("Chroma 컬렉션 '%s'이 아직 없습니다. 색인(I-02) 후 셀 수 있습니다.", config.CHROMA_COLLECTION)
            return []

        # Chroma는 빈 where({})를 오류로 처리하므로 None으로 넘긴다.
        result = collection.get(where=where or None, include=["metadatas"])
    return list(result["metadatas"] or [])
