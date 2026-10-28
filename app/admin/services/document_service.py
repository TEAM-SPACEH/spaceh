"""A-01·A-02 문서 업로드·삭제·재색인·중복 검사."""

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.admin.repositories import document_repository as repository
from app.ingestion.indexing.embedder import DocumentEmbedder
from app.ingestion.indexing.indexer import DocumentIndexer
from app.ingestion.parsers.loader import MAX_DOCUMENT_BYTES
from app.ingestion.pipeline import ingest_document
from app.ingestion.preprocessing.metadata import build_metadata
from core import config
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN


def _admin(user: dict) -> dict:
    """A-01 로그인 세션의 ID로 최신 관리자 권한을 확인한다."""
    if not isinstance(user, dict) or type(user.get("id")) is not int:
        raise PermissionError("관리자 권한이 필요합니다.")
    current = repository.find_active_admin(user["id"])
    if not current or current["role"] not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        raise PermissionError("관리자 권한이 필요합니다.")
    return current


def _check_company(admin: dict, company_id: str) -> None:
    """A-01 계열사 관리자의 타사 등록·중복 조회를 차단한다."""
    if not isinstance(company_id, str) or not company_id:
        raise ValueError("기업을 선택해 주세요.")
    if admin["role"] == ROLE_COMPANY_ADMIN and admin["company_id"] != company_id:
        raise PermissionError("자사 문서만 관리할 수 있습니다.")


def get_upload_companies(user: dict) -> list[dict]:
    """A-01 화면이 권한을 판단하지 않도록 업로드 가능한 회사만 반환한다."""
    admin = _admin(user)
    return [company for company in repository.list_active_companies()
            if admin["role"] == ROLE_SUPER_ADMIN
            or company["company_id"] == admin["company_id"]]


def _read_file(file) -> tuple[str, bytes]:
    """A-01 업로드 객체의 파일명·크기를 검증하고 원본 바이트를 읽는다."""
    name = getattr(file, "name", None)
    if (not isinstance(name, str) or not name.strip() or len(name) > 255
            or any(c in name for c in ("/", "\\", "\x00"))
            or Path(name).suffix.lower() not in (".pdf", ".docx", ".pptx")):
        raise ValueError("경로 없는 PDF·DOCX·PPTX 파일명이 필요합니다.")
    position = file.tell()
    try:
        file.seek(0)
        content = file.read(MAX_DOCUMENT_BYTES + 1)
    finally:
        file.seek(position)
    if not isinstance(content, bytes) or not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("비어 있지 않은 20 MiB 이하 문서가 필요합니다.")
    return name, content


def _error(error: Exception, stage: str) -> str:
    """A-01 예외 원문의 본문·경로·인증 정보가 화면이나 DB에 노출되지 않게 한다."""
    if isinstance(error, PermissionError):
        return "해당 기업의 문서를 관리할 권한이 없습니다."
    return f"{stage} 실패 ({type(error).__name__})"


def check_duplicate_document(file, company_id: str, user: dict) -> dict:
    """A-01 관리 권한 확인 후 같은 기업의 원본 SHA-256 중복 여부를 반환한다."""
    try:
        admin = _admin(user)
        _check_company(admin, company_id)
        _, content = _read_file(file)
        duplicate = repository.find_duplicate(company_id, sha256(content).hexdigest())
        return {"is_duplicate": bool(duplicate), "document": duplicate, "error_message": ""}
    except Exception as error:
        return {"is_duplicate": False, "document": None,
                "error_message": _error(error, "중복 검사")}


def _cleanup_failed_chunks(doc_id: str, message: str) -> str:
    """DB 실패 상태가 확정된 문서만 정리하고 정리 오류를 안내한다."""
    try:
        repository.delete_document_chunks(doc_id)
    except Exception:
        return message + " / 색인 청크 정리 실패: 문서 상태를 확인한 뒤 재처리해 주세요."
    return message


def upload_document(file, metadata: dict, user: dict) -> dict:
    """A-01 권한·중복 확인 후 원본과 DB를 저장하고 색인 결과를 반영한다."""
    doc_id = ""
    stage = "업로드 검증"
    registered = False
    registration_attempted = False
    file_created = False
    path = None
    try:
        admin = _admin(user)
        if not isinstance(metadata, dict):
            raise ValueError("등록 정보가 필요합니다.")
        company_id = metadata.get("company_id")
        _check_company(admin, company_id)
        company = next((c for c in repository.list_active_companies()
                        if c["company_id"] == company_id), None)
        if company is None:
            raise ValueError("활성 회사가 아닙니다.")
        name, content = _read_file(file)
        now = datetime.now()
        published = metadata.get("published_date") or now.date()
        if isinstance(published, str):
            published = date.fromisoformat(published)
        if type(published) is not date:
            raise ValueError("작성일 형식을 확인하세요.")
        doc_id = uuid4().hex
        info = dict(metadata, company_name=company["name"], file_name=name,
                    file_format=Path(name).suffix[1:].lower(), source_type="internal",
                    source_url="", published_date=published, created_at=now,
                    is_group_shared=False)
        build_metadata(doc_id, info, {})
        is_mock = metadata.get("is_mock", False)
        if type(is_mock) is not bool:
            raise ValueError("목데이터 여부는 bool이어야 합니다.")
        # 원본 제목은 검색용 마스킹 결과와 분리해 DB에 보존한다.
        info["title"] = (info.get("title") or "").strip() or Path(name).stem
        content_hash = sha256(content).hexdigest()
        duplicate = repository.find_duplicate(company_id, content_hash)
        if duplicate:
            return {"doc_id": duplicate["doc_id"], "index_status": "duplicate",
                    "chunk_count": 0, "error_message": "", "document": duplicate}
        stage = "원본 저장·문서 등록"
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        path = config.UPLOAD_DIR / (doc_id + Path(name).suffix.lower())
        with path.open("xb") as output:
            file_created = True
            output.write(content)
        document = dict(info, doc_id=doc_id, file_path=str(path), content_hash=content_hash,
                        uploaded_by=admin["id"], is_mock=is_mock, index_status="pending")
        registration_attempted = True
        duplicate = repository.insert_document(document)
        if duplicate:
            path.unlink()
            path = None
            return {"doc_id": duplicate["doc_id"], "index_status": "duplicate",
                    "chunk_count": 0, "error_message": "", "document": duplicate}
        registered = True
        stage = "색인"
        repository.update_index_status(doc_id, "indexing", 0, "")
        with DocumentIndexer() as indexer:
            result = ingest_document(path, doc_id, info, {}, DocumentEmbedder(), indexer)
        stage = "색인 상태 저장"
        repository.update_index_status(doc_id, result["index_status"],
                                       result["chunk_count"], result["error_message"])
        if result["index_status"] == "failed":
            result["error_message"] = _cleanup_failed_chunks(doc_id, result["error_message"])
        return result
    except Exception as error:
        message = _error(error, stage)
        if registered:
            try:
                repository.update_index_status(doc_id, "failed", 0, message)
            except Exception:
                message = "DB 상태 저장 실패: 문서 상태를 확인한 뒤 재처리해 주세요."
            else:
                # 완료 커밋의 응답만 유실됐을 수 있어 실패 저장이 확인된 뒤 지운다.
                message = _cleanup_failed_chunks(doc_id, message)
        elif registration_attempted:
            # commit 응답 유실이면 등록됐을 수 있으므로 원본을 지우지 않는다.
            message += " / DB 등록 여부와 보관된 원본을 확인해 주세요."
        elif path is not None and file_created:
            # 등록 전 실패한 원본만 지우고, 등록된 실패 문서는 A-02 재처리용으로 남긴다.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                message += " / 미등록 원본 정리 실패"
        return {"doc_id": doc_id if registration_attempted else "", "index_status": "failed",
                "chunk_count": 0, "error_message": message}
