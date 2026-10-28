"""A-01·A-02 문서 업로드·삭제·재색인·중복 검사."""

import logging
import math
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.admin.paging import clamp
from app.admin.repositories import document_repository as repository
from app.admin.services.audit_service import record_audit_log
from app.ingestion.indexing.embedder import DocumentEmbedder
from app.ingestion.indexing.indexer import DocumentIndexer
from app.ingestion.parsers.loader import MAX_DOCUMENT_BYTES
from app.ingestion.pipeline import ingest_document
from app.ingestion.preprocessing.metadata import build_metadata
from core import config
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN
from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ACCESS_LEVELS, ACCESS_PUBLIC


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


# ---------------------------------------------------------------------------
# A-02 문서 목록 조회·삭제·재색인 (이 구역 아래는 A-02 전용이다. 위의 A-01 함수는 바꾸지 않는다)
# ---------------------------------------------------------------------------

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 대기(pending)·처리 중(indexing)으로 이 시간(분) 넘게 멈춘 문서는 서버가 중간에 죽은 것으로 보고 삭제·재색인을 허용한다.
STALE_MINUTES = 30

DOC_TYPES = {"report": "보고서", "disclosure": "공시", "manual": "매뉴얼",
             "spec": "사양서", "intro": "소개자료", "memo": "메모"}
SECURITY_LEVELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}
INDEX_STATUS_LABELS = {"pending": "대기", "indexing": "색인 중", "done": "완료", "failed": "실패"}

# audit_logs.action 값
ACTION_DOCUMENT_DELETE = "document_delete"
ACTION_DOCUMENT_REINDEX = "document_reindex"

logger = logging.getLogger(__name__)


def _message(error: Exception, stage: str) -> str:
    """A-02 이 모듈이 직접 만든 안내 문구는 그대로, 그 밖의 예외는 원문 없이 단계·종류만 보여 준다."""
    if isinstance(error, (PermissionError, ValueError, LookupError)):
        return str(error.args[0]) if error.args else f"{stage} 실패"
    return f"{stage} 실패 ({type(error).__name__})"


def _record(user: dict, action: str, doc_id: str, document: dict | None,
            blocked: bool, reason: str | None, detail: dict | None = None) -> None:
    """A-02 감사 로그를 남긴다. 기록 실패가 삭제·재색인 결과를 가리지 않도록 로그만 남기고 넘어간다."""
    try:
        record_audit_log(
            user.get("id") if isinstance(user, dict) else None, action, doc_id, None, blocked, reason,
            target_type="document", doc_ids=[doc_id],
            doc_companies=[document["company_id"]] if document else None, context_detail=detail,
        )
    except Exception:
        logger.exception("A-02 감사 로그 기록 실패: action=%s doc_id=%s", action, doc_id)


def _load_manageable(admin: dict, doc_id: str) -> dict:
    """A-02 문서를 조회하고 이 관리자가 관리할 수 있는지(자사 문서인지) 확인한다."""
    if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 100:
        raise ValueError("문서를 선택해 주세요.")
    document = repository.get_managed_document(doc_id)
    if document is None:
        raise LookupError("문서를 찾을 수 없습니다. 이미 삭제되었을 수 있습니다.")
    _check_company(admin, document["company_id"])
    return document


def _resolve_original(file_path: str | None) -> Path | None:
    """A-02 documents.file_path가 가리키는 원본을 업로드 폴더 안에서만 찾는다. 없거나 폴더 밖이면 None."""
    if not file_path:
        return None
    upload_dir = config.UPLOAD_DIR.resolve()
    for candidate in (config.ROOT_DIR / file_path, upload_dir / file_path):
        resolved = candidate.resolve()
        # "../../.env" 같은 값으로 업로드 폴더 밖 파일을 가리키지 못하게 한다.
        if resolved.is_relative_to(upload_dir) and resolved.is_file():
            return resolved
    return None


def _is_claimable(row: dict) -> bool:
    """A-02 삭제·재색인을 시작할 수 있는 상태인지 판단한다 (저장소 claim_document의 조건과 같다)."""
    return row["index_status"] in ("done", "failed") or bool(row.get("is_stale"))


def _filter_value(value, allowed) -> str:
    """A-02 허용된 값만 통과시키고 나머지는 "전체"(빈 문자열)로 본다."""
    return value if isinstance(value, str) and value in allowed else ""


def get_document_filter_options() -> dict:
    """A-02 필터 화면용 문서 유형·보안 등급·색인 상태 선택지({코드: 화면 이름})를 반환한다.

    기업 선택지는 권한에 따라 달라서 get_upload_companies(user)로 따로 받는다.
    """
    return {"doc_types": DOC_TYPES, "security_levels": SECURITY_LEVELS,
            "index_statuses": INDEX_STATUS_LABELS}


def get_document_list(user: dict, filters: dict | None, page: int = 1,
                      size: int = DEFAULT_PAGE_SIZE) -> dict:
    """A-02 관리자 역할·소속·필터를 적용해 문서 목록과 색인 상태를 한 페이지 조회한다.

    filters: company_id, doc_type, access_level, index_status, keyword (없으면 전체).
        계열사 관리자는 company_id를 무시하고 자사로 고정한다.
    반환: {"documents": [...], "total", "page", "size", "total_pages"}.
        각 문서에 status_label·can_reindex·can_delete를 붙여 화면이 권한·상태를 판단하지 않게 한다.
    PermissionError: 관리자가 아니거나 소속 없는 계열사 관리자
    """
    admin = _admin(user)
    filters = filters if isinstance(filters, dict) else {}
    if admin["role"] == ROLE_COMPANY_ADMIN:
        if not admin["company_id"]:
            # None(전체)으로 처리하면 권한이 넓어지므로 소속 없는 관리자는 거부한다.
            raise PermissionError("소속 계열사가 없는 관리자는 문서를 관리할 수 없습니다.")
        company_id = admin["company_id"]
    else:
        raw = filters.get("company_id")
        company_id = raw.strip() if isinstance(raw, str) and raw.strip() else None
    keyword = filters.get("keyword")
    keyword = keyword.strip()[:100] if isinstance(keyword, str) else ""
    size = clamp(size, 1, MAX_PAGE_SIZE)
    page = clamp(page, 1, 10 ** 6)
    args = (company_id,
            _filter_value(filters.get("doc_type"), DOC_TYPES),
            _filter_value(filters.get("access_level"), ACCESS_LEVELS),
            _filter_value(filters.get("index_status"), INDEX_STATUS_LABELS),
            keyword)
    rows, total = repository.list_managed_documents(*args, size, (page - 1) * size, STALE_MINUTES)
    total_pages = max(1, math.ceil(total / size))
    if page > total_pages:
        # 필터를 좁히는 사이 건수가 줄어 페이지가 범위를 벗어났으면 마지막 페이지로 맞춘다.
        page = total_pages
        rows, total = repository.list_managed_documents(*args, size, (page - 1) * size, STALE_MINUTES)
    documents = []
    for row in rows:
        claimable = _is_claimable(row)
        documents.append(dict(
            row,
            is_group_shared=bool(row["is_group_shared"]),
            status_label=INDEX_STATUS_LABELS.get(row["index_status"], row["index_status"]),
            can_delete=claimable,
            # DART 공시는 원본 파일이 없어 다시 색인할 수 없다.
            can_reindex=claimable and row["source_type"] == "internal",
        ))
    return {"documents": documents, "total": total, "page": page, "size": size,
            "total_pages": total_pages}


def _remove_original(document: dict) -> str:
    """A-02 원본 파일을 지우고, 못 지웠으면 안내 문구를 반환한다. 이미 없거나 DART 문서면 빈 문자열."""
    path = _resolve_original(document.get("file_path"))
    if path is None:
        return ""
    try:
        path.unlink()
    except OSError:
        return "원본 파일을 지우지 못했습니다. 저장 폴더를 확인해 주세요."
    return ""


def _restore_status(doc_id: str, previous: dict) -> None:
    """A-02 선점해 둔 처리 중 표시를 이전 상태로 되돌린다. 되돌리지 못해도 오래되면 다시 시도할 수 있다."""
    try:
        repository.update_index_status(
            doc_id, previous["index_status"], previous["chunk_count"], previous["error_message"] or "")
    except Exception:
        logger.exception("A-02 처리 중 표시를 되돌리지 못했습니다: doc_id=%s", doc_id)


def delete_document(doc_id: str, user: dict) -> dict:
    """A-02 문서를 삭제한다. 검색 노출을 먼저 끊는 순서로 지운다.

    1) 처리 중 표시로 선점(같은 문서의 재색인·공유 변경·다른 삭제를 막는다)
    2) Chroma 청크 삭제 — 실패하면 DB는 그대로 두고 이전 상태로 되돌린다
    3) MySQL 문서 행 삭제 — 실패하면 "실패"·청크 0으로 남겨 재시도·재색인을 할 수 있게 한다
    4) 원본 파일 삭제 — 실패해도 문서는 이미 사라졌으므로 경고만 한다
    열람 요청·승인은 문서 행 삭제 때 DB가 함께 지운다.

    반환: {"doc_id", "status": "deleted"|"failed", "error_message", "warning"}
    """
    document = None
    stage = "삭제 준비"
    try:
        admin = _admin(user)
        document = _load_manageable(admin, doc_id)
        previous = repository.claim_document(doc_id, STALE_MINUTES)
        if previous is None:
            raise ValueError("색인 중이거나 처리 중인 문서는 삭제할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    except Exception as error:
        message = _message(error, stage)
        _record(user, ACTION_DOCUMENT_DELETE, doc_id if isinstance(doc_id, str) else "", document,
                isinstance(error, PermissionError), message, {"result": "failed", "stage": stage})
        return {"doc_id": doc_id, "status": "failed", "error_message": message, "warning": ""}

    stage = "검색 색인 삭제"
    try:
        repository.delete_document_chunks(doc_id)
        stage = "문서 정보 삭제"
        repository.delete_document_row(doc_id)
    except Exception as error:
        message = _message(error, stage)
        if stage == "검색 색인 삭제":
            _restore_status(doc_id, previous)
        else:
            # 청크는 이미 지워졌다. 완료로 두면 검색에 없는 문서가 "완료"로 보이므로 실패로 표시한다.
            try:
                repository.update_index_status(doc_id, "failed", 0, message)
            except Exception:
                message += " / 문서 상태를 확인해 주세요."
        _record(user, ACTION_DOCUMENT_DELETE, doc_id, document, False, None,
                {"result": "failed", "stage": stage})
        return {"doc_id": doc_id, "status": "failed", "error_message": message, "warning": ""}

    warning = _remove_original(document)
    _record(user, ACTION_DOCUMENT_DELETE, doc_id, document, False, None,
            {"result": "success", "title": document["title"][:100], "chunk_count": previous["chunk_count"]})
    return {"doc_id": doc_id, "status": "deleted", "error_message": "", "warning": warning}


def request_reindex(doc_id: str, user: dict) -> dict:
    """A-02 기존 원본과 등록 정보로 문서를 다시 색인하고 결과를 문서 상태에 반영한다.

    A-01 업로드와 달리 그룹사 공유·보안 등급은 DB의 현재 값을 그대로 Chroma 메타데이터에 싣는다.
    (공유 ON이던 문서가 재색인으로 타사 검색에서 사라지거나 반대로 넓어지지 않게 한다.)
    새 색인이 실패하면 청크를 지우고 "실패"로 둔다. 새 내용과 옛 내용이 섞인 채 검색되는 것을 막는다.

    반환: {"doc_id", "index_status", "chunk_count", "error_message"} (ingest_document와 같은 모양)
    """
    document = None
    stage = "재색인 준비"
    claimed = None
    try:
        admin = _admin(user)
        document = _load_manageable(admin, doc_id)
        if document["source_type"] != "internal" or not document["file_path"]:
            raise ValueError("원본 파일이 없는 문서(DART 공시)는 재색인할 수 없습니다.")
        path = _resolve_original(document["file_path"])
        if path is None:
            raise ValueError("원본 파일을 찾을 수 없습니다. 문서를 삭제한 뒤 다시 올려 주세요.")
        claimed = repository.claim_document(doc_id, STALE_MINUTES)
        if claimed is None:
            raise ValueError("이미 색인 중이거나 처리 중인 문서입니다. 잠시 후 다시 시도해 주세요.")
        stage = "색인"
        info = {
            "company_id": document["company_id"], "company_name": document["company_name"],
            "doc_type": document["doc_type"], "title": document["title"],
            "file_name": document["file_name"], "file_format": document["file_format"],
            "source_type": document["source_type"], "source_url": document["source_url"] or "",
            "published_date": document["published_date"], "access_level": document["access_level"],
            "is_group_shared": bool(document["is_group_shared"]),
        }
        with DocumentIndexer() as indexer:
            result = ingest_document(path, doc_id, info, {}, DocumentEmbedder(), indexer)
    except Exception as error:
        message = _message(error, stage)
        if claimed is not None:
            # 선점한 뒤에 난 오류(임베더 준비 실패 등): 청크 상태를 알 수 없으니 실패로 기록하고 정리한다.
            result = {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                      "error_message": message}
        else:
            _record(user, ACTION_DOCUMENT_REINDEX, doc_id if isinstance(doc_id, str) else "", document,
                    isinstance(error, PermissionError), message, {"result": "failed", "stage": stage})
            return {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0, "error_message": message}

    try:
        repository.update_index_status(doc_id, result["index_status"], result["chunk_count"],
                                       result["error_message"])
    except Exception:
        # 처리 중으로 남지만 STALE_MINUTES 뒤에는 다시 시도할 수 있다.
        result = {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                  "error_message": "DB 상태 저장 실패: 문서 상태를 확인한 뒤 다시 시도해 주세요."}
    else:
        if result["index_status"] == "failed":
            result["error_message"] = _cleanup_failed_chunks(doc_id, result["error_message"])
    _record(user, ACTION_DOCUMENT_REINDEX, doc_id, document, False, None,
            {"result": "success" if result["index_status"] == "done" else "failed",
             "chunk_count": result["chunk_count"], "error": result["error_message"][:200]})
    return result
