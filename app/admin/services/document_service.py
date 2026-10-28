"""A-01·A-02 문서 업로드·삭제·재색인·중복 검사."""

import logging
import math
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.admin.paging import clamp
from app.admin.repositories import document_repository as repository
from app.admin.services import access_service
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

# 한 화면에 보여 줄 문서 수와 한 번에 요청할 수 있는 최대 수. 화면에서 온 값이 이상해도 이 범위로 맞춘다.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 대기(pending)·처리 중(indexing)으로 이 시간(분) 넘게 멈춘 문서는 서버가 중간에 죽은 것으로 보고 삭제·재색인을 허용한다.
STALE_MINUTES = 30

# 문서 유형 코드와 화면 이름. 코드는 DB(documents.doc_type)와 Chroma 에 그대로 저장되는 값이고, 이름은 화면에만 쓴다.
# 업로드 화면(A-01)의 선택지와 같은 값이다.
DOC_TYPES = {"report": "보고서", "disclosure": "공시", "manual": "매뉴얼",
             "spec": "사양서", "intro": "소개자료", "memo": "메모"}
# 보안 등급 코드와 화면 이름. 화면 용어는 "기밀"이다 ("대외비" 아님).
SECURITY_LEVELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}
# 색인 상태: 대기 → 색인 중 → 완료/실패. 화면에는 이름으로 보여 주고, 필터에도 이 값을 쓴다.
INDEX_STATUS_LABELS = {"pending": "대기", "indexing": "색인 중", "done": "완료", "failed": "실패"}

# audit_logs.action 값
ACTION_DOCUMENT_DELETE = "document_delete"
ACTION_DOCUMENT_REINDEX = "document_reindex"

logger = logging.getLogger(__name__)


def _message(error: Exception, stage: str) -> str:
    """A-02 이 모듈이 직접 만든 안내 문구는 그대로, 그 밖의 예외는 원문 없이 단계·종류만 보여 준다."""
    # PermissionError·ValueError·LookupError 는 이 파일이 직접 "사용자가 읽어도 되는 안내 문구"로 만들어 던진 오류다.
    # 그래서 문구를 그대로 보여 준다.
    if isinstance(error, (PermissionError, ValueError, LookupError)):
        return str(error.args[0]) if error.args else f"{stage} 실패"
    # 그 밖의 예외(DB·Chroma·임베딩 오류)는 원문에 경로·인증 정보·본문이 섞일 수 있어 화면·DB·감사 로그로 보내지 않는다.
    # 어느 단계에서 어떤 종류가 났는지만 알려 준다.
    return f"{stage} 실패 ({type(error).__name__})"


def _record(user: dict, action: str, doc_id: str, document: dict | None,
            blocked: bool, reason: str | None, detail: dict | None = None) -> None:
    """A-02 감사 로그를 남긴다. 기록 실패가 삭제·재색인 결과를 가리지 않도록 로그만 남기고 넘어간다."""
    try:
        # 4번째 인자(ip)는 명세 시그니처를 맞추려고 None 을 넘긴다 (audit_logs 에 IP 컬럼이 없어 저장되지 않는다).
        # doc_companies 는 "어느 회사 문서였는지"로, 계열사 관리자가 감사 로그에서 자사 관련 기록만 볼 때 쓰인다.
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
    # 문서를 먼저 조회해야 "어느 회사 문서인지" 알 수 있고, 그래야 이 관리자가 다룰 권한이 있는지 판단한다.
    document = repository.get_managed_document(doc_id)
    if document is None:
        raise LookupError("문서를 찾을 수 없습니다. 이미 삭제되었을 수 있습니다.")
    # 계열사 관리자는 자사 문서만 가능하다 (최종 어드민은 통과). 타사 문서면 PermissionError 가 나서 아무것도 바뀌지 않는다.
    # 화면에서 버튼을 숨기는 것은 안내일 뿐이라, 이 확인은 화면과 무관하게 항상 서비스가 한다.
    _check_company(admin, document["company_id"])
    return document


def _resolve_original(file_path: str | None) -> Path | None:
    """A-02 documents.file_path가 가리키는 원본을 업로드 폴더 안에서만 찾는다. 없거나 폴더 밖이면 None."""
    if not file_path:
        return None
    upload_dir = config.UPLOAD_DIR.resolve()
    # DB 의 file_path 가 "data/uploads/a.docx"(저장소 기준)인지 "a.docx"(업로드 폴더 기준)인지 둘 다 있을 수 있어 두 곳을 모두 찾아본다.
    for candidate in (config.ROOT_DIR / file_path, upload_dir / file_path):
        resolved = candidate.resolve()
        # "../../.env" 같은 값으로 업로드 폴더 밖 파일을 가리키지 못하게 한다.
        if resolved.is_relative_to(upload_dir) and resolved.is_file():
            return resolved
    return None


def _is_claimable(row: dict) -> bool:
    """A-02 삭제·재색인을 시작할 수 있는 상태인지 판단한다 (저장소 claim_document의 조건과 같다)."""
    # 끝난 문서이거나, 대기·색인 중이라도 오래(STALE_MINUTES) 멈춘 문서만 건드릴 수 있다.
    # 화면은 이 값으로 버튼을 켜고 끄지만, 실제 판단은 저장소의 claim_document 가 DB 에서 한 번 더 한다.
    return row["index_status"] in ("done", "failed") or bool(row.get("is_stale"))


def _filter_value(value, allowed) -> str:
    """A-02 허용된 값만 통과시키고 나머지는 "전체"(빈 문자열)로 본다."""
    # 화면 값은 사용자가 바꿀 수 있으므로, 허용된 코드(DOC_TYPES·보안 등급·색인 상태)가 아니면 "전체"로 취급한다.
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
    # 1단계: 권한. _admin 이 세션이 아니라 DB 에서 현재 역할·활성 상태를 다시 읽는다 (그 사이 강등·비활성화됐을 수 있다).
    # 필터 입력이 dict 가 아니어도 안전하게 빈 필터로 본다.
    filters = filters if isinstance(filters, dict) else {}
    # 2단계: 조회 범위. 계열사 관리자는 화면에서 무엇을 골랐든 자사로 고정한다 (타사 문서 목록을 볼 수 없다).
    # 최종 어드민은 고른 회사만, 안 골랐으면 전체(None)를 본다.
    if admin["role"] == ROLE_COMPANY_ADMIN:
        if not admin["company_id"]:
            # None(전체)으로 처리하면 권한이 넓어지므로 소속 없는 관리자는 거부한다.
            raise PermissionError("소속 계열사가 없는 관리자는 문서를 관리할 수 없습니다.")
        company_id = admin["company_id"]
    else:
        raw = filters.get("company_id")
        company_id = raw.strip() if isinstance(raw, str) and raw.strip() else None
    # 3단계: 입력 보정. 검색어는 앞뒤 공백을 떼고 100자로 자르며, 글자가 아니면 빈 검색어로 본다.
    keyword = filters.get("keyword")
    keyword = keyword.strip()[:100] if isinstance(keyword, str) else ""
    # 페이지 번호와 크기가 0·음수·너무 큰 수·글자여도 안전한 범위(1~100, 페이지 1 이상)로 맞춘다.
    size = clamp(size, 1, MAX_PAGE_SIZE)
    page = clamp(page, 1, 10 ** 6)
    # 저장소에 넘길 조건. 허용되지 않는 필터 값은 여기서 "전체"(빈 문자열)가 된다.
    args = (company_id,
            _filter_value(filters.get("doc_type"), DOC_TYPES),
            _filter_value(filters.get("access_level"), ACCESS_LEVELS),
            _filter_value(filters.get("index_status"), INDEX_STATUS_LABELS),
            keyword)
    rows, total = repository.list_managed_documents(*args, size, (page - 1) * size, STALE_MINUTES)
    # 마지막 페이지 번호. 문서가 0건이어도 1페이지로 센다.
    # 필터를 좁히는 사이 건수가 줄어 요청한 페이지가 범위를 넘으면, 마지막 페이지로 맞춰 다시 읽는다 (빈 화면 방지).
    total_pages = max(1, math.ceil(total / size))
    if page > total_pages:
        # 필터를 좁히는 사이 건수가 줄어 페이지가 범위를 벗어났으면 마지막 페이지로 맞춘다.
        page = total_pages
        rows, total = repository.list_managed_documents(*args, size, (page - 1) * size, STALE_MINUTES)
    # 화면이 권한·상태를 직접 판단하지 않도록, 서비스가 각 문서에 "삭제 가능?"·"재색인 가능?"을 계산해서 붙인다.
    documents = []
    for row in rows:
        # 처리할 수 있는 상태인지(끝났거나 멈춘 문서). 삭제·재색인 모두 이 조건을 먼저 통과해야 한다.
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
    # 원본이 없거나(DART 공시) 업로드 폴더 밖을 가리키면 None 이라 아무것도 지우지 않는다. 폴더 밖 파일은 절대 지우지 않는다.
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
            # 선점하기 전의 상태·청크 수·오류 문구로 되돌린다. 삭제 단계가 실패해 "처리 중"으로 남는 문서가 생기지 않게 한다.
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
    # 1단계: 권한 확인 → 문서 조회 → 선점(처리 중 표시). 여기서 하나라도 막히면 아무것도 지우지 않고 실패 결과만 돌려준다.
    # stage 는 실패했을 때 "어느 단계에서" 났는지 사용자에게 알리려는 이름표다.
    stage = "삭제 준비"
    try:
        admin = _admin(user)
        document = _load_manageable(admin, doc_id)
        # 선점: 지금 색인 중이거나 다른 삭제가 진행 중이면 None 이다. 그러면 지우지 않는다 (색인 도중에 청크를 지우면 되살아날 수 있다).
        previous = repository.claim_document(doc_id, STALE_MINUTES)
        # None = 선점 실패(이미 다른 작업이 처리 중). 안내 문구를 띄우고 중단한다.
        if previous is None:
            raise ValueError("색인 중이거나 처리 중인 문서는 삭제할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    except Exception as error:
        message = _message(error, stage)
        _record(user, ACTION_DOCUMENT_DELETE, doc_id if isinstance(doc_id, str) else "", document,
                isinstance(error, PermissionError), message, {"result": "failed", "stage": stage})
        return {"doc_id": doc_id, "status": "failed", "error_message": message, "warning": ""}

    # 2~3단계: 검색에서 먼저 사라지게 한다 (Chroma 청크 → MySQL 행).
    # 순서가 중요한 이유: MySQL 행을 먼저 지우고 Chroma 삭제가 실패하면, 주인 없는 청크가 검색에 계속 노출된다.
    # Chroma 를 먼저 지우면 실패해도 문서 행이 남아 있어 다시 시도할 수 있다.
    stage = "검색 색인 삭제"
    try:
        repository.delete_document_chunks(doc_id)
        stage = "문서 정보 삭제"
        repository.delete_document_row(doc_id)
    except Exception as error:
        message = _message(error, stage)
        # Chroma 삭제 단계에서 실패 → 아무것도 지워지지 않았으므로 선점하기 전 상태로 되돌린다.
        # MySQL 삭제 단계에서 실패 → 청크는 이미 지워졌다. 이때는 되돌릴 수 없으니 "실패"·청크 0 으로 표시해 재색인이나 재시도를 할 수 있게 한다.
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

    # 4단계: 원본 파일. 문서 행은 이미 지워졌으므로 파일 삭제가 실패해도 삭제 자체는 성공으로 보고, 경고 문구만 돌려준다.
    # 5단계: 감사 로그. 기록이 실패해도 삭제 결과를 뒤집지 않는다 (_record 가 오류를 삼키고 로그만 남긴다).
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
    # 재색인 순서: 권한 → 재색인 가능한 문서인지 → 원본 파일 확인 → 선점 → 색인 → 결과 저장 → 감사 로그.
    # 선점은 마지막 확인 뒤에 한다. 그래야 "원본 없음" 같은 이유로 거부할 때 문서가 "처리 중"으로 잘못 남지 않는다.
    stage = "재색인 준비"
    claimed = None
    try:
        admin = _admin(user)
        document = _load_manageable(admin, doc_id)
        # DART 공시는 원본 파일이 없고 I-05 가 다시 수집한다. 다시 색인할 원본이 없으므로 거부한다 (삭제는 가능).
        if document["source_type"] != "internal" or not document["file_path"]:
            raise ValueError("원본 파일이 없는 문서(DART 공시)는 재색인할 수 없습니다.")
        # 원본이 지워졌거나 업로드 폴더 밖을 가리키면 재색인할 수 없다. 안내대로 삭제 후 다시 올리게 한다.
        path = _resolve_original(document["file_path"])
        if path is None:
            raise ValueError("원본 파일을 찾을 수 없습니다. 문서를 삭제한 뒤 다시 올려 주세요.")
        # 선점. 같은 문서를 두 사람이 동시에 재색인하면 한쪽만 통과하고 다른 쪽은 "이미 처리 중"을 받는다 (청크가 두 번 쌓이는 것 방지).
        # 선점하면 A-03 공유 변경도 막힌다 (색인이 끝난 문서만 공유를 바꿀 수 있다).
        # A-03 공유 변경과 같은 잠금 안에서 "선점 → 문서 다시 읽기"를 한다. 그러지 않으면 위에서 읽은 뒤 선점하기 전에
        # 공유가 바뀌었을 때 옛 공유 값이 Chroma 에 실려 MySQL 과 어긋난다 (공유를 껐는데 타사 검색에 남는 방향).
        # 선점한 뒤에는 A-03 이 이 문서를 못 바꾸므로, 이때 다시 읽은 값이 색인이 끝날 때까지 유효하다.
        # (이 잠금은 한 프로세스 안의 요청만 직렬화한다. 서버를 여러 개 띄우면 분산 잠금이 필요하다.)
        with access_service._GROUP_SHARE_LOCK:
            claimed = repository.claim_document(doc_id, STALE_MINUTES)
            if claimed is None:
                raise ValueError("이미 색인 중이거나 처리 중인 문서입니다. 잠시 후 다시 시도해 주세요.")
            document = repository.get_managed_document(doc_id)
        stage = "색인"
        # ingest_document 에 넘길 등록 정보. A-01 업로드는 공유를 항상 OFF 로 시작하지만, 재색인은 이미 올라간 문서다.
        # 그래서 DB 의 현재 값(회사·보안 등급·공유 상태·제목·작성일)을 그대로 쓴다. 이 값이 Chroma 메타데이터가 되고,
        # 검색 권한 필터(S-03)가 그 값을 본다. 공유 상태를 틀리게 실으면 타사 검색에 노출되거나 사라진다.
        info = {
            "company_id": document["company_id"], "company_name": document["company_name"],
            "doc_type": document["doc_type"], "title": document["title"],
            "file_name": document["file_name"], "file_format": document["file_format"],
            "source_type": document["source_type"], "source_url": document["source_url"] or "",
            "published_date": document["published_date"], "access_level": document["access_level"],
            # MySQL 의 TINYINT(0/1)을 bool 로 바꾼다 (메타데이터 검증이 bool 또는 0·1 만 허용한다).
            "is_group_shared": bool(document["is_group_shared"]),
        }
        with DocumentIndexer() as indexer:
            result = ingest_document(path, doc_id, info, {}, DocumentEmbedder(), indexer)
    except Exception as error:
        message = _message(error, stage)
        # 선점한 뒤에 난 오류(예: 임베딩 객체 준비 실패)다. 그냥 돌려보내면 문서가 "처리 중"으로 남으니,
        # 실패 결과로 만들어 아래의 상태 저장·청크 정리를 같이 타게 한다. 선점 전에 난 오류(권한·원본 없음)는 여기서 바로 돌려준다.
        if claimed is not None:
            # 선점한 뒤에 난 오류(임베더 준비 실패 등): 청크 상태를 알 수 없으니 실패로 기록하고 정리한다.
            result = {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                      "error_message": message}
        else:
            _record(user, ACTION_DOCUMENT_REINDEX, doc_id if isinstance(doc_id, str) else "", document,
                    isinstance(error, PermissionError), message, {"result": "failed", "stage": stage})
            return {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0, "error_message": message}

    try:
        # 색인 결과(완료/실패·청크 수·오류 문구)를 문서 행에 저장한다. "처리 중"을 풀어 주는 단계이기도 하다.
        # 여기서 DB 오류가 나면 상태가 "처리 중"으로 남지만, STALE_MINUTES 가 지나면 다시 시도할 수 있다.
        # 새 색인이 실패한 경우에는 저장 후에 청크를 지운다(새 내용과 옛 내용이 섞여 검색되는 것을 막는다).
        repository.update_index_status(doc_id, result["index_status"], result["chunk_count"],
                                       result["error_message"])
    except Exception:
        # 처리 중으로 남지만 STALE_MINUTES 뒤에는 다시 시도할 수 있다.
        result = {"doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                  "error_message": "DB 상태 저장 실패: 문서 상태를 확인한 뒤 다시 시도해 주세요."}
    else:
        if result["index_status"] == "failed":
            result["error_message"] = _cleanup_failed_chunks(doc_id, result["error_message"])
    # 결과(성공/실패)를 감사 로그에 남긴다. blocked 는 "권한 때문에 막힘"이라는 뜻이라 색인 실패는 False 로 두고 detail 에 결과를 적는다.
    _record(user, ACTION_DOCUMENT_REINDEX, doc_id, document, False, None,
            {"result": "success" if result["index_status"] == "done" else "failed",
             "chunk_count": result["chunk_count"], "error": result["error_message"][:200]})
    return result
