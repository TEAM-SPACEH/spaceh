"""I-01~I-03 문서 적재 연결. DB 등록·상태 반영과 객체 종료는 호출자가 맡는다."""

from pathlib import Path

from app.ingestion.indexing.embedder import DocumentEmbedder
from app.ingestion.indexing.indexer import DocumentIndexer
from app.ingestion.parsers.loader import load_document
from app.ingestion.preprocessing.chunker import split_into_chunks
from app.ingestion.preprocessing.masking import mask_sensitive_data
from app.ingestion.preprocessing.metadata import build_metadata


def ingest_document(
    file_path: str | Path, doc_id: str, document_info: dict,
    chunking_config: dict, embedder: DocumentEmbedder, indexer: DocumentIndexer,
) -> dict:
    """I-01~I-03 로딩부터 색인까지 실행하고 처리 상태·저장 수·안전한 오류를 반환한다."""
    stage = "파일 로딩"
    try:
        blocks = load_document(file_path)
        stage = "메타데이터 구성"
        metadata = build_metadata(doc_id, document_info, {})
        if metadata["file_format"] != Path(file_path).suffix[1:].lower():
            raise ValueError("등록한 형식과 파일 확장자가 다릅니다.")
        stage = "개인정보 마스킹"
        masked_blocks, _ = mask_sensitive_data(blocks)
        stage = "청킹"
        chunks = split_into_chunks(masked_blocks, metadata, chunking_config)
        stage = "임베딩"
        vectors = embedder.embed_chunks(chunks)
        stage = "색인 저장"
        stored = indexer.index_chunks(doc_id, chunks, vectors)
        if (stored["doc_id"] != doc_id or stored["index_status"] != "done"
                or type(stored["chunk_count"]) is not int
                or stored["chunk_count"] != len(chunks)):
            raise ValueError("색인 결과가 요청한 문서·청크와 일치하지 않습니다.")
        return {"doc_id": doc_id, "index_status": "done",
                "chunk_count": stored["chunk_count"], "error_message": ""}
    except Exception as error:
        # 예외 원문에는 본문·경로·인증 정보가 섞일 수 있어 DB·화면으로 보내지 않는다.
        return {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                "error_message": f"{stage} 단계 실패 ({type(error).__name__})"}
