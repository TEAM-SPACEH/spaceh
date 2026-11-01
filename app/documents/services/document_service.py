"""S-05 원문 보기: 권한 재확인, 뷰어용 문서 정보, PDF 페이지 이미지, 원본 다운로드, DART 뷰어 주소."""

# ─────────────────────────────────────────────────────────────
# services 파일 = "주방"이에요.
#   - 권한 확인, 파일 읽기, 이미지 만들기 같은 실제 일을 해요.
#   - 화면 코드(st.*)는 쓰지 않아요. (팀 규칙)
#
# 출처(source)는 S-04 rag_service.generate_answer()가 돌려주는 모양을 그대로 받아요.
#   {"text", "company", "filename", "location", "doc_id", "chunk_id", "citation_number"}
# ─────────────────────────────────────────────────────────────

import io
import logging
import re
from pathlib import Path

import pypdfium2 as pdfium

from app.admin.services.audit_service import record_audit_log
from app.documents.repositories.document_repository import find_by_id
from app.permissions.services.permission_service import check_search_permission
from core import config

logger = logging.getLogger(__name__)

# DART 공시 뷰어 주소 틀. documents.source_url이 비어 있을 때 접수번호(doc_no)로 만들어요.
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}"

# PDF를 몇 배 크기로 그릴지. 2배면 글씨가 선명하고, 더 키우면 느려져요.
PAGE_RENDER_SCALE = 2

# 감사 로그(A-04) 행위 코드와 차단 사유
AUDIT_VIEW = "view_document"   # 원문 열람
AUDIT_DOWNLOAD = "download"    # 원본 다운로드
BLOCK_NO_PERMISSION = "권한 없음"


def get_source_page(source: dict) -> int:
    """S-05 출처에서 원문 뷰어로 열 페이지 번호를 꺼낸다. 알 수 없으면 0."""
    # S-04 출처에는 페이지 숫자 칸이 없고 "p.3" / "페이지 3" 같은 글자(location)만 있어요.
    # 그래서 page 칸이 생기면 그걸 먼저 쓰고, 없으면 글자에서 숫자를 뽑아요.
    page = source.get("page")
    if isinstance(page, int) and page > 0:
        return page

    # "p.3", "페이지 3"처럼 페이지를 뜻하는 표기에서만 숫자를 뽑아요.
    # "슬라이드 5", "4.2 고장 대처" 같은 다른 위치 표기를 페이지 번호로 착각하지 않기 위해서예요.
    match = re.search(r"(?:p\.|페이지)\s*(\d+)", str(source.get("location", "")))
    return int(match.group(1)) if match else 0


def get_viewer_document(doc_id: str, user: dict, *, audit: bool = True) -> dict | None:
    """S-05 권한을 다시 확인해 원문 뷰어에 보여 줄 문서 정보를 돌려준다. 문서가 없으면 None."""
    # audit: 감사 로그를 남길지. Streamlit은 버튼을 누를 때마다 화면 코드를 처음부터 다시 실행해서
    #   뷰어가 열려 있는 동안 이 함수가 계속 불려요. 그때마다 기록하면 1번 연 게 여러 건으로 쌓여요.
    #   그래서 화면은 "새로 연 출처"일 때만 audit=True로 불러요. (search_documents(audit=)와 같은 방식)
    # * 뒤의 인자는 이름을 꼭 써서 넘겨야 해요(audit=False). 숫자·순서 실수를 막아요.
    document = find_by_id(doc_id)
    if document is None:
        logger.warning("S-05 문서 없음 doc_id=%s", doc_id)
        return None

    # 권한이 없으면 제목·회사만 돌려줘요.
    # 화면이 "권한 없는 문서" 안내(no_permission_notice)에 제목을 보여 줘야 해서예요.
    # 본문·파일 위치는 절대 넘기지 않아요.
    if not check_search_permission(user, document):
        logger.warning("S-05 열람 차단 user_id=%s doc_id=%s", user.get("id"), doc_id)
        # 막힌 열람도 감사 로그에 남겨요. 관리자가 "누가 남의 문서를 열려 했는지" 볼 수 있게요.
        if audit:
            _record_audit(user, AUDIT_VIEW, document, blocked=True, reason=BLOCK_NO_PERMISSION)
        return {
            "can_view": False,
            "doc_id": document["doc_id"],
            "title": document["title"],
            "company_id": document["company_id"],
        }

    # 권한 확인을 통과한 열람을 감사 로그에 남겨요.
    if audit:
        _record_audit(user, AUDIT_VIEW, document, blocked=False)
    return {
        "can_view": True,
        "doc_id": document["doc_id"],
        "title": document["title"],
        "company_id": document["company_id"],
        "access_level": document["access_level"],
        "file_name": document["file_name"],
        "file_format": document["file_format"],
        "source_type": document["source_type"],
        # 뷰어 오른쪽 "문서 정보" 칸용. 권한이 있을 때만 넘겨요 (위 can_view False 응답에는 넣지 않아요).
        "company_name": document.get("company_name") or document["company_id"],
        "is_group_shared": bool(document.get("is_group_shared")),
        "page_count": document.get("page_count") or 0,
        "published_date": document.get("published_date"),
        "pii_masked_count": document.get("pii_masked_count") or 0,
        "chunk_count": document.get("chunk_count") or 0,
        "indexed_at": document.get("updated_at"),
        # 적재(I-05) 때 저장한 DART 주소가 있으면 그대로 쓰고, 없으면 접수번호로 만들어요.
        "dart_url": document.get("source_url") or get_dart_viewer_url("", document.get("doc_no") or ""),
    }


def get_page_image(doc_id: str, page: int, user: dict) -> bytes | None:
    """S-05 권한을 다시 확인한 뒤 PDF 해당 페이지를 PNG 이미지로 만든다."""
    # 📌 메소드 명세서에 없는 함수예요. 화면(views)은 권한 판단을 할 수 없어서 서비스로 만들었어요.
    # 페이지를 넘길 때마다 불려서 감사 로그는 남기지 않아요(audit_action 없음). 열람 기록은
    # get_viewer_document()가 뷰어를 열 때 한 번 남겨요. 📌 팀 합의 후 확정
    # _는 "문서 정보는 여기서 안 써요"라는 뜻이에요.
    _, file_path = _get_viewable_file(doc_id, user)
    if file_path is None or file_path.suffix.lower() != ".pdf":
        return None

    pdf = pdfium.PdfDocument(file_path)
    try:
        # len(pdf) = 전체 페이지 수. 범위 밖 번호는 그릴 수 없어요.
        if not 1 <= page <= len(pdf):
            logger.warning("S-05 잘못된 페이지 doc_id=%s page=%s", doc_id, page)
            return None
        # 사람은 페이지를 1부터, pypdfium2는 0부터 세서 page - 1 이에요.
        image = pdf[page - 1].render(scale=PAGE_RENDER_SCALE).to_pil()
    finally:
        # 오류가 나도 PDF를 꼭 닫아요. 안 닫으면 Windows에서 파일이 잠겨 삭제·재색인이 안 돼요.
        pdf.close()

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def download_document(doc_id: str, user: dict) -> bytes | None:
    """S-05 요청 시 문서 접근 권한을 재검증한 뒤 원본 파일을 반환한다."""
    # 📌 명세서 출력은 void인데, st.download_button에 파일 내용이 필요해서 bytes를 돌려줘요.
    # audit_action을 넘기면 권한 차단을 헬퍼 안에서 기록해요.
    # (밖에서는 "문서 없음"과 "권한 없음"이 둘 다 None이라 구분할 수 없어서예요)
    document, file_path = _get_viewable_file(doc_id, user, audit_action=AUDIT_DOWNLOAD)
    if file_path is None:
        return None

    file_bytes = file_path.read_bytes()
    # 파일을 실제로 읽은 뒤에 기록해요. 읽다가 실패하면 "다운로드함"으로 남지 않게요.
    _record_audit(user, AUDIT_DOWNLOAD, document, blocked=False)
    return file_bytes


def get_dart_viewer_url(corp_code: str, rcp_no: str) -> str:
    """S-05 공시 고유번호를 이용하여 DART 공시 원문 뷰어 URL을 반환한다."""
    # 📌 명세서 위치(integrations/dart_client)가 폴더 구조에 없어서 여기에 두었어요.
    # corp_code는 명세서 입력이라 받지만, 뷰어 주소는 접수번호만 있으면 만들 수 있어요.
    # DART 접수번호는 숫자 14자리라서, 다른 값이면 주소를 만들지 않아요.
    if not re.fullmatch(r"\d{14}", rcp_no or ""):
        return ""
    return DART_VIEWER_URL.format(rcp_no=rcp_no)


def _get_viewable_file(
    doc_id: str, user: dict, audit_action: str | None = None,
) -> tuple[dict | None, Path | None]:
    """문서를 찾고 권한을 다시 확인한 뒤, (문서 정보, 열어도 되는 원본 파일 경로)를 돌려준다."""
    # 페이지 이미지와 다운로드가 똑같은 확인을 거쳐야 해서 한 곳에 모았어요.
    # 문서 정보도 같이 돌려주는 이유: 다운로드 감사 로그에 회사 코드가 필요해서예요(DB를 두 번 안 읽게).
    # 막히면 (None, None)을 돌려줘요.
    document = find_by_id(doc_id)
    if document is None:
        return None, None

    # 열기 직전에 권한을 다시 확인해요.
    # 검색 뒤에 공유가 꺼지거나 승인이 취소됐을 수 있고, 문서 번호를 바꿔 직접 요청할 수도 있어서예요.
    if not check_search_permission(user, document):
        logger.warning("S-05 파일 접근 차단 user_id=%s doc_id=%s", user.get("id"), doc_id)
        # 부른 쪽이 행위 코드(audit_action)를 줬을 때만 차단을 기록해요. (다운로드 O, 페이지 이미지 X)
        if audit_action:
            _record_audit(user, audit_action, document, blocked=True, reason=BLOCK_NO_PERMISSION)
        return None, None

    return document, _resolve_upload_path(document.get("file_path"))


def _record_audit(
    user: dict, action: str, document: dict, blocked: bool, reason: str | None = None,
) -> None:
    """S-05 원문 열람·다운로드를 감사 로그(A-04)에 1건 남긴다. 기록이 실패해도 본 기능은 계속한다."""
    try:
        record_audit_log(
            user.get("id"),          # 행동한 사용자 (users.id)
            action,                  # view_document / download
            document["doc_id"],      # 대상 문서 ID
            None,                    # ip_address: 저장하지 않는 칸이라 None (A-04 규칙)
            blocked,                 # 권한으로 막혔으면 True
            reason,                  # 차단 사유 (허용이면 None)
            target_type="document",
            doc_ids=[document["doc_id"]],
            doc_companies=[document["company_id"]],  # 관리자가 회사별로 걸러 볼 때 써요
        )
    except Exception:
        # DB 오류 등으로 기록이 실패해도 원문 보기·다운로드는 막지 않아요. (A-04 공통 규칙)
        # logger.exception은 오류 내용과 위치(트레이스백)까지 서버 로그에 남겨요.
        logger.exception("감사 로그 기록 실패(%s) doc_id=%s", action, document.get("doc_id"))


def _resolve_upload_path(file_path: str | None) -> Path | None:
    """documents.file_path를 실제 경로로 바꾸고, data/uploads 밖 파일이면 거부한다."""
    if not file_path:  # DART 공시는 원본 파일이 없어요
        return None

    upload_dir = config.UPLOAD_DIR.resolve()
    # file_path가 "data/uploads/a.pdf"(저장소 기준)인지 "a.pdf"(uploads 기준)인지 아직 정해지지 않아서 둘 다 찾아봐요.
    for candidate in (config.ROOT_DIR / file_path, upload_dir / file_path):
        resolved = candidate.resolve()
        # "../../.env" 같은 값으로 uploads 밖의 파일을 꺼내 가지 못하게 막아요.
        if resolved.is_relative_to(upload_dir) and resolved.is_file():
            return resolved

    logger.error("S-05 원본 파일 없음 file_path=%s", file_path)
    return None
