"""I-02 청크·임베딩을 저장하고 재색인 시 오래된 청크를 제거한다."""

from contextlib import ExitStack
from math import isfinite
from pathlib import Path
import re

from core import config
from core.chroma import open_chroma_client


class DocumentIndexer:
    """I-02 공통 Chroma 연결을 보관한다. with 블록 또는 close()로 종료한다."""

    def __init__(self, chroma_config: dict | None = None,
                 collection_name: str | None = None) -> None:
        """I-02 연결 설정의 path와 컬렉션명을 사용해 저장 대상을 준비한다."""
        settings = {} if chroma_config is None else chroma_config
        if not isinstance(settings, dict) or set(settings) - {"path"}:
            raise ValueError("Chroma 연결 설정은 path만 포함하는 dict여야 합니다.")
        path = settings.get("path", config.CHROMA_DIR)
        name = config.CHROMA_COLLECTION if collection_name is None else collection_name
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ValueError("Chroma 저장 경로가 필요합니다.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Chroma 컬렉션명이 필요합니다.")
        # 컬렉션 준비가 실패하더라도 이미 열린 연결을 반드시 닫는다.
        with ExitStack() as resources:
            self.client = resources.enter_context(open_chroma_client(path))
            self.collection = self.client.get_or_create_collection(
                name=name, embedding_function=None,
            )
            self._resources = resources.pop_all()
        self._closed = False

    def __enter__(self):
        """with 블록에서 같은 색인 객체를 사용한다."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """예외 발생 여부와 관계없이 Windows 파일 잠금을 해제한다."""
        self.close()

    def close(self) -> None:
        """I-02 보관한 Chroma 연결을 닫으며 여러 번 호출해도 안전하다."""
        self._resources.close()
        self._closed = True

    def index_chunks(self, doc_id: str, chunks: list[dict],
                     embeddings: list[list[float]]) -> dict:
        """I-02 문서 청크를 교체하고 doc_id·chunk_count·index_status를 반환한다."""
        if self._closed:
            raise RuntimeError("종료된 색인 객체는 사용할 수 없습니다.")
        if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 100:
            raise ValueError("문서 ID는 1~100자 문자열이어야 합니다.")
        if (not isinstance(chunks, list) or not chunks
                or not isinstance(embeddings, list) or len(chunks) != len(embeddings)):
            raise ValueError("비어 있지 않은 청크와 같은 개수의 임베딩이 필요합니다.")
        ids, texts, metadatas = [], [], []
        dimension = None
        # 모든 배치를 먼저 검증해 뒤쪽 입력 오류로 기존 색인을 일부만 바꾸지 않게 한다.
        for chunk, vector in zip(chunks, embeddings):
            if not isinstance(chunk, dict):
                raise ValueError("각 청크는 dict여야 합니다.")
            chunk_id, text = chunk.get("chunk_id"), chunk.get("text")
            metadata = chunk.get("metadata")
            if not isinstance(chunk_id, str):
                raise ValueError("청크 ID는 문자열이어야 합니다.")
            owner, _, number = chunk_id.rpartition("#")
            # 마지막 # 앞은 문서 ID, 뒤는 청커의 양수 ASCII 순번으로 고정해 충돌을 막는다.
            if (owner != doc_id or not re.fullmatch(r"(?:[0-9]{4}|[1-9][0-9]{4,})", number)
                    or number == "0000"):
                raise ValueError("청크 ID는 {doc_id}#{순번:04d} 형식이어야 합니다.")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("청크 본문이 필요합니다.")
            if (not isinstance(metadata, dict) or metadata.get("doc_id") != doc_id
                    or not isinstance(metadata.get("company_id"), str)
                    or not metadata["company_id"].strip()
                    or metadata.get("access_level") not in ("public", "internal", "confidential")
                    or type(metadata.get("is_group_shared")) is not bool
                    or (metadata["is_group_shared"] and metadata["access_level"] != "internal")):
                raise ValueError("문서 ID·회사·보안 등급·공유 메타데이터를 확인하세요.")
            if any(not isinstance(key, str) or not key.strip()
                   or type(value) not in (str, int, float, bool)
                   or (type(value) is float and not isfinite(value))
                   for key, value in metadata.items()):
                raise ValueError("메타데이터는 문자열 키와 유한한 단일 값만 허용합니다.")
            if (not isinstance(vector, list) or not vector
                    or any(type(value) not in (int, float) or not isfinite(value)
                           for value in vector)):
                raise ValueError("임베딩은 비어 있지 않은 유한한 숫자 목록이어야 합니다.")
            if dimension is not None and len(vector) != dimension:
                raise ValueError("모든 임베딩의 차원이 같아야 합니다.")
            dimension = len(vector)
            ids.append(chunk_id)
            texts.append(text)
            metadatas.append(metadata)
        if len(set(ids)) != len(ids):
            raise ValueError("중복 청크 ID는 저장할 수 없습니다.")

        batch_size = self.client.get_max_batch_size()
        # ID의 접두사만으로는 다른 문서의 기존 청크 소유권을 보장할 수 없다.
        for start in range(0, len(ids), batch_size):
            existing = self.collection.get(
                ids=ids[start:start + batch_size], include=["metadatas"],
            )
            if any(not isinstance(metadata, dict) or metadata.get("doc_id") != doc_id
                   for metadata in existing["metadatas"]):
                raise ValueError("다른 문서가 소유하거나 소유자를 확인할 수 없는 청크 ID입니다.")

        old_ids = self.collection.get(where={"doc_id": doc_id}, include=[])["ids"]
        for start in range(0, len(ids), batch_size):
            stop = start + batch_size
            self.collection.upsert(
                ids=ids[start:stop], documents=texts[start:stop],
                embeddings=embeddings[start:stop], metadatas=metadatas[start:stop],
            )
        # 저장이 끝나기 전에 기존 청크를 지우면 실패 시 원래 문서까지 잃는다.
        stale_ids = sorted(set(old_ids) - set(ids))
        for start in range(0, len(stale_ids), batch_size):
            self.collection.delete(ids=stale_ids[start:start + batch_size],
                                   where={"doc_id": doc_id})
        return {"doc_id": doc_id, "chunk_count": len(ids), "index_status": "done"}
