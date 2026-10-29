"""S-05 내부 문서 뷰어 (Figma 03): 권한 재확인 후 PDF 해당 페이지와 근거 문단, 문서 정보를 3단으로 보여 준다."""

import html
import logging

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import (
    citation_html,
    company_tag_html,
    empty_state,
    no_permission_notice,
    security_badge_html,
)
from app.documents.services.document_service import (
    download_document,
    get_page_image,
    get_source_page,
    get_viewer_document,
)
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.permissions.services.permission_service import request_document_access

logger = logging.getLogger(__name__)

# 파일 형식 → 다운로드할 때 브라우저에 알려 줄 파일 종류
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# 오른쪽 위 파일 형식 타일에 적는 글자 (색은 ui.py의 .sh-v-type-* 가 정한다)
FORMAT_LABELS = {"pdf": "PDF", "docx": "DOCX", "pptx": "PPTX", "xlsx": "XLSX", "hwp": "HWP", "dart_xml": "DART"}

# 확대·축소 단계(%)와 100%일 때 페이지 그림의 가로 폭(px). 폭은 Figma 원문 카드 안쪽 폭(720 - 좌우 여백 72×2)이다.
ZOOM_STEPS = (50, 75, 100, 125, 150, 200)
DEFAULT_ZOOM = 100
PAGE_IMAGE_WIDTH = 574

# 왼쪽 쪽 미리보기: 근거 쪽 앞 2장, 뒤 1장 (Figma)
THUMBS_BEFORE = 2
THUMBS_AFTER = 1

DEFAULT_BACK_LABEL = "검색 결과로 돌아가기"


def render_selected_source(user: dict | None = None, back_label: str = DEFAULT_BACK_LABEL) -> None:
    """S-05 출처 배지에서 고른 출처를 원문 뷰어로 연다. 고른 출처가 없으면 안내만 표시한다."""
    # 출처 배지와 원문 뷰어를 잇는 다리예요.
    # 배지의 [원문 보기]는 고른 출처를 세션(SELECTED_SOURCE_KEY)에 넣기만 하고,
    # 이 함수가 그 값을 꺼내 render_document_viewer()에 doc_id와 위치를 넘겨요.
    # 답변 화면(S-04)에서는 이렇게 두 줄만 쓰면 돼요.
    #   render_source_badge(result["sources"])
    #   render_selected_source()
    user = user or get_current_user()  # 검색 화면(S-01)처럼 넘겨받은 사용자가 없으면 로그인 사용자를 써요
    if not user:
        st.warning("로그인 후 원문을 볼 수 있습니다.")
        return

    source = st.session_state.get(SELECTED_SOURCE_KEY)
    if source is None:
        empty_state("출처의 [원문 보기]를 누르면 여기에 원문이 표시됩니다.")
        return

    render_document_viewer(source["doc_id"], source, user, back_label)


def render_document_viewer(doc_id: str, location: dict, user: dict, back_label: str = DEFAULT_BACK_LABEL) -> None:
    """S-05 권한 재확인 후 PDF 해당 페이지 이미지와 근거 문단을 표시한다."""
    # location = 배지에서 고른 출처 그대로예요 (S-04 sources 한 개).
    #   {"text": 근거 문단, "company", "filename", "location": "p.3", "doc_id", ...}
    # 📌 명세서에는 location 모양이 없어서 이렇게 정했어요. 팀에 공유가 필요해요.

    # ① 권한 재확인 + 문서 정보 (판단은 services가 해요)
    document = get_viewer_document(doc_id, user)
    if document is None:
        st.error("문서를 찾을 수 없습니다. 삭제되었거나 다시 색인 중일 수 있습니다.")
        _render_back_button(back_label)
        return

    # ② 권한이 없으면 제목만 보여 주고 본문·근거 문단은 보여 주지 않아요.
    if not document["can_view"]:
        # [열람 권한 요청] 버튼을 누르면 사유 입력 폼을 연다(M-03). 연 상태를 세션에 저장해
        # 사유를 적다가 화면이 재실행돼도 폼이 닫히지 않게 한다.
        open_key = f"s05_request_open_{doc_id}"
        if no_permission_notice(document["title"], location["company"], key=f"s05_{doc_id}"):
            st.session_state[open_key] = True
        if st.session_state.get(open_key):
            _render_access_request_form(doc_id, user)
        _render_back_button(back_label)
        return

    _render_viewer(document, location, user, back_label)


def _render_viewer(document: dict, location: dict, user: dict, back_label: str) -> None:
    """③ 권한이 있는 문서를 Figma 03 모양 3단으로 보여 준다: 쪽 미리보기 | 원문 | 문서 정보."""
    doc_id = document["doc_id"]
    is_dart = document["source_type"] == "dart"
    is_pdf = not is_dart and document["file_format"] == "pdf"
    page = get_source_page(location)  # 알 수 없으면 0

    with st.container(key="s05_viewer"):
        if is_pdf and document["page_count"]:
            thumbs_col, page_col, info_col = st.columns([112, 924, 340])
            with thumbs_col:
                _render_thumbnails(doc_id, page, document["page_count"], user)
        else:
            page_col, info_col = st.columns([924, 340])

        with page_col, st.container(key="s05_page_area"):
            _render_page(document, location, user, page, is_pdf, is_dart, back_label)

        with info_col, st.container(key="s05_info"):
            _render_info(document, location, user, is_dart)


def _render_thumbnails(doc_id: str, page: int, page_count: int, user: dict) -> None:
    """왼쪽 쪽 미리보기. 근거가 있는 쪽을 테두리와 초록 번호로 표시한다."""
    anchor = page if 1 <= page <= page_count else 1
    first = max(1, anchor - THUMBS_BEFORE)
    last = min(page_count, anchor + THUMBS_AFTER)
    with st.container(key="s05_thumbs"):
        st.html(f'<div class="sh-v-thumb-count">{int(page_count)}쪽</div>')
        for number in range(first, last + 1):
            is_current = number == page
            with st.container(key="s05_thumb_current" if is_current else f"s05_thumb_{number}"):
                image = get_page_image(doc_id, number, user)  # 쪽마다 권한을 다시 확인해요
                if image is not None:
                    st.image(image, width="stretch")
            if is_current:
                st.html(f'<div class="sh-v-thumb-no">{number}</div>')


def _render_page(document: dict, location: dict, user: dict, page: int, is_pdf: bool, is_dart: bool,
                 back_label: str) -> None:
    """가운데 칸: 위쪽 도구 줄(돌아가기·확대·축소)과 원문 카드(쪽 그림과 근거 문단)."""
    doc_id = document["doc_id"]
    zoom_key = f"s05_zoom_{doc_id}"
    zoom = st.session_state.get(zoom_key, DEFAULT_ZOOM)

    with st.container(horizontal=True, key="s05_toolbar"):
        _render_back_button(back_label)
        if is_pdf:
            # 확대·축소는 쪽 그림이 있는 PDF에서만 뜻이 있어서 그때만 보여 줘요.
            with st.container(horizontal=True, key="s05_zoom"):
                st.button("-", key="s05_zoom_out", on_click=_change_zoom, args=(zoom_key, -1),
                          disabled=zoom <= ZOOM_STEPS[0])
                st.html(f'<div class="sh-v-zoom">{int(zoom)}%</div>')
                st.button("+", key="s05_zoom_in", on_click=_change_zoom, args=(zoom_key, 1),
                          disabled=zoom >= ZOOM_STEPS[-1])

    with st.container(key="s05_page"):
        page_text = str(page) if page else str(location.get("location") or "")
        st.html(
            f'<div class="sh-v-page-head"><span>{html.escape(document["title"])}</span>'
            f"<span>{html.escape(page_text)}</span></div>"
        )

        # 근거 문단을 쪽 그림 위에 둬요. 그림 아래에 두면 스크롤해야만 보여서예요.
        _render_evidence(location)

        # DART 공시는 우리 앱에 원본이 없어서 DART 뷰어로 보내요.
        if is_dart:
            if document["dart_url"]:
                st.link_button("DART에서 원문 보기", document["dart_url"])
            else:
                st.warning("DART 접수번호가 없어 원문으로 연결할 수 없습니다.")
            return

        # PDF는 해당 페이지를 이미지로 보여 줘요.
        if is_pdf:
            image = get_page_image(doc_id, page, user)
            if image is None:
                st.warning("페이지 이미지를 불러올 수 없습니다. 근거 문단만 표시합니다.")
            else:
                st.image(image, width=round(PAGE_IMAGE_WIDTH * zoom / 100))
        else:
            # DOCX·PPTX 텍스트 뷰어는 다음 단계라, 지금은 근거 문단만 보여 줘요.
            st.info("이 형식은 페이지 이미지를 지원하지 않습니다. 근거 문단만 표시합니다.")


def _render_evidence(location: dict) -> None:
    """근거 문단을 옐로 하이라이트 줄로 보여 준다. 데이터에서 온 글자라 escape한다."""
    st.html(f'<div class="sh-v-para sh-v-para-hl">{html.escape(str(location.get("text") or ""))}</div>')


def _render_info(document: dict, location: dict, user: dict, is_dart: bool) -> None:
    """오른쪽 칸: 문서 머리글, 이 문단을 쓴 답변, 문서 정보, 원문 내려받기."""
    file_format = document["file_format"]
    sub = ", ".join(
        part for part in (
            # DOCX는 page_count가 쪽 수가 아니라 문단 번호 기준이라, 쪽 수는 PDF만 보여 줘요.
            f"{document['page_count']}쪽" if file_format == "pdf" and document["page_count"] else "",
            _date_text(document["published_date"], "%Y.%m.%d 작성"),
        ) if part
    )
    st.html(
        '<div class="sh-v-info-head">'
        f'<span class="sh-v-type sh-v-type-{html.escape(file_format)}">{html.escape(FORMAT_LABELS.get(file_format, file_format.upper()))}</span>'
        f'<div class="sh-v-tags">{company_tag_html(document["company_id"])}{security_badge_html(document["access_level"])}</div>'
        "</div>"
        f'<div class="sh-v-title">{html.escape(document["title"])}</div>'
        f'<div class="sh-v-sub">{html.escape(sub)}</div>'
    )

    answer_html = _answer_html(location)
    if answer_html:
        st.html(answer_html)

    indexed = ", ".join(
        part for part in (
            f"청크 {document['chunk_count']}개",
            _date_text(document["indexed_at"], "%m.%d 완료"),
        ) if part
    )
    masked = f"{document['pii_masked_count']}건 가림" if document["pii_masked_count"] else "없음"
    rows = (
        ("소유 회사", document["company_name"]),
        ("그룹사 공유", "켜짐" if document["is_group_shared"] else "꺼짐"),
        ("개인정보", masked),
        ("색인", indexed),
    )
    st.html(
        '<div class="sh-v-section"><div class="sh-v-section-title">문서 정보</div><div class="sh-v-rows">'
        + "".join(
            f'<div class="sh-v-row"><span>{html.escape(label)}</span><span>{html.escape(str(value))}</span></div>'
            for label, value in rows
        )
        + "</div></div>"
    )

    if not is_dart:  # DART 공시는 받을 원본 파일이 없어요
        with st.container(key="s05_download"):
            _render_download(document, user)
            st.html('<div class="sh-v-note">내려받을 때 권한을 다시 확인하고 감사 로그에 남깁니다.</div>')


def _answer_html(location: dict) -> str:
    """"이 문단을 쓴 답변" 상자. 출처에 답변 번호가 없으면 만들지 않는다."""
    # answer_title·answer_note는 답변 화면(S-04)·보고서가 출처에 넣어 주면 쓰는 선택 값이에요.
    # 아직 없으면 출처 번호와 문서 위치만 보여 줘요.
    try:
        number_html = citation_html(location["citation_number"])
    except (KeyError, TypeError, ValueError):
        return ""
    title = location.get("answer_title") or f"출처 {location['citation_number']}번 근거 문단"
    note = location.get("answer_note") or location.get("location") or ""
    return (
        '<div class="sh-v-section"><div class="sh-v-section-title">이 문단을 쓴 답변</div>'
        f'<div class="sh-v-answer"><div class="sh-v-answer-head">{number_html}<span>{html.escape(str(title))}</span></div>'
        f'<div class="sh-v-answer-sub">{html.escape(str(note))}</div></div></div>'
    )


def _date_text(value, fmt: str) -> str:
    """날짜·시각을 화면 글자로 바꾼다. 값이 없으면 빈 글자."""
    return value.strftime(fmt) if hasattr(value, "strftime") else ""


def _change_zoom(zoom_key: str, direction: int) -> None:
    """확대(+1)·축소(-1) 한 단계. 단계 밖으로는 가지 않는다."""
    current = st.session_state.get(zoom_key, DEFAULT_ZOOM)
    index = ZOOM_STEPS.index(current) if current in ZOOM_STEPS else ZOOM_STEPS.index(DEFAULT_ZOOM)
    st.session_state[zoom_key] = ZOOM_STEPS[max(0, min(len(ZOOM_STEPS) - 1, index + direction))]


def _close_viewer() -> None:
    """뷰어를 닫는다. 고른 출처를 세션에서 지우면 호출한 화면이 원래 모양으로 돌아와요."""
    st.session_state.pop(SELECTED_SOURCE_KEY, None)


def _render_back_button(label: str) -> None:
    """[검색 결과로 돌아가기]: 누르면 뷰어를 닫는다. 콜백이라 따로 st.rerun()을 부르지 않아도 다시 그려져요."""
    st.button(label, key="s05_back", type="tertiary", on_click=_close_viewer)


def _render_access_request_form(doc_id: str, user: dict) -> None:
    """S-05 뷰어에서 권한 없는 문서의 열람 권한을 요청한다(M-03).

    사유(5~500자)를 받아 permission_service에 넘긴다. 판단·검증·저장은 모두 서비스가 하고,
    여기서는 입력을 받아 넘기고 결과만 안내한다(계층 규칙: views → services). 검색 화면의
    요청 폼과 같은 흐름이다.
    """
    reason = st.text_area("요청 사유 (5~500자)", key=f"s05_reason_{doc_id}")
    if not st.button("요청 보내기", key=f"s05_send_{doc_id}"):
        return

    try:
        registered = request_document_access(user["id"], doc_id, reason)
    except Exception:
        # 동시 요청 시 DB 데드락(1213) 등으로 예외가 올라올 수 있다. 앱을 멈추지 않고 안내한다.
        logger.exception("S-05 열람 권한 요청 등록 실패")
        st.error("요청 처리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if registered:
        st.success("열람 권한을 요청했습니다. 소유 회사 관리자의 승인 후 볼 수 있습니다.")
        # 이미 요청했으니 폼을 닫는다(같은 문서에 또 열지 않게).
        st.session_state.pop(f"s05_request_open_{doc_id}", None)
    else:
        st.error("요청을 등록하지 못했습니다. 사유(5~500자)를 확인하거나, 이미 요청한 문서인지 확인해 주세요.")


def _render_download(document: dict, user: dict) -> None:
    """원본 다운로드: 버튼을 누르는 순간 권한을 다시 확인하고 파일을 읽는다."""
    doc_id = document["doc_id"]

    def read_file_on_click() -> bytes:
        # data에 파일 내용 대신 "함수"를 넘기면, Streamlit은 화면을 그릴 때가 아니라
        # 사용자가 버튼을 누른 순간에 이 함수를 실행해요.
        # 그래서 화면을 띄운 뒤에 공유가 꺼지거나 승인이 취소돼도, 누르는 순간의 권한으로 다시 판단해요.
        # (예전에는 미리 읽은 파일을 세션에 넣어 둬서, 권한이 사라진 뒤에도 그 파일을 받을 수 있었어요.)
        file_bytes = download_document(doc_id, user)  # 여기서 권한 재확인 + 파일 읽기
        if file_bytes is None:
            # 오류를 내면 Streamlit이 다운로드를 멈추고 브라우저에 실패를 알려요.
            # 빈 파일을 돌려주지 않는 이유: 사용자가 "받아졌다"고 오해하지 않게 하려고요.
            # 이 함수 안에서는 st.* 화면 명령이 무시돼서 안내 문구 대신 오류를 내요.
            raise PermissionError(f"S-05 원본 다운로드 거부 doc_id={doc_id}")
        return file_bytes

    st.download_button(
        "원문 내려받기",
        data=read_file_on_click,  # 괄호 없이 함수 자체를 넘겨요. 괄호를 붙이면 지금 바로 실행돼 버려요.
        file_name=document["file_name"],
        mime=MIME_TYPES.get(document["file_format"], "application/octet-stream"),
        key=f"s05_download_{doc_id}",
        width="stretch",
    )
