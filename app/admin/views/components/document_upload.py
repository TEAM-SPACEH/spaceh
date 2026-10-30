"""A-01 문서 업로드 모달 (Figma 08)."""

import html

import streamlit as st

from app.admin.services.document_service import get_upload_companies, upload_document
from app.admin.views.components.document_labels import DOC_TYPE_NAMES, format_tile_html
from app.admin.views.components.duplicate_notice import render_duplicate_notice
from app.common.ui import ACCESS_LABELS, show_text, upload_status_html

# 안내 문구는 실제 동작과 같아야 한다 (파일당 20MB, PDF·DOCX·PPTX만 읽는다).
UPLOAD_HINT = "파일당 최대 20MB • PDF, DOCX, PPTX"
_NOTE_TEXT = "그룹사 공유는 기본으로 꺼져 있습니다. 올린 뒤 문서 목록에서 켤 수 있고, 기밀 문서는 공유할 수 없습니다."
_INFO_ICON_URL = "app/static/icons/info.svg"


def clear_upload_files() -> None:
    """A-01 파일 선택과 처리 결과를 초기화한다."""
    st.session_state["upload-generation"] = st.session_state.get("upload-generation", 0) + 1
    st.session_state.pop("upload-results", None)
    st.session_state.pop("upload-files", None)


def _queue_files(widget_key: str) -> None:
    """A-01 선택한 파일을 목록에 보관하고 업로더를 다시 비운다."""
    files = st.session_state.setdefault("upload-files", {})
    for file in st.session_state.get(widget_key, []):
        files[file.file_id] = file
    st.session_state["upload-generation"] = st.session_state.get("upload-generation", 0) + 1


def _remove_file(file_id: str) -> None:
    """A-01 선택 목록에서만 파일과 결과를 제거하고 저장된 문서는 보존한다."""
    st.session_state.get("upload-files", {}).pop(file_id, None)
    st.session_state.get("upload-results", {}).pop(file_id, None)


def _format_size(size: int) -> str:
    """파일 크기를 "4.2MB"·"320KB"처럼 짧게 쓴다."""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    return f"{max(round(size / 1024), 1)}KB"


def _file_type(file_name: str) -> str:
    """파일 이름의 확장자로 형식 타일 종류를 정한다 (타일에는 확장자만 보인다)."""
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


@st.dialog("문서 올리기", width="small")
def render_document_upload(user: dict) -> None:
    """A-01 여러 파일의 등록 정보를 받아 파일별 저장·색인 결과를 표시한다."""
    try:
        companies = get_upload_companies(user)
    except Exception:
        st.error("업로드 가능한 기업을 조회할 수 없습니다. 관리자 권한과 DB 연결을 확인해 주세요.")
        return
    if not companies:
        st.info("업로드 가능한 기업이 없습니다.")
        return

    names = {company["company_id"]: company["name"] for company in companies}
    # 부제는 아래 "소속 기업"에서 고른 값을 따른다. 위젯을 만들기 전이라 직전 선택(없으면 첫 기업)을 읽는다.
    chosen = st.session_state.get("upload-company")
    st.html('<span class="sh-upload-dialog-marker" hidden></span>')
    st.html(f'<div class="sh-up-sub">{html.escape(names.get(chosen, next(iter(names.values()))))} 문서로 등록됩니다.</div>')

    widget_key = f"document-files-{st.session_state.get('upload-generation', 0)}"
    with st.container(key="upload-picker"):
        selected = st.file_uploader(
            "파일을 여기로 끌어다 놓거나 파일을 선택하세요.",
            type=["pdf", "docx", "pptx"], accept_multiple_files=True,
            max_upload_size=20, key=widget_key, label_visibility="collapsed",
            on_change=_queue_files, args=(widget_key,),
        )
    queue = st.session_state.setdefault("upload-files", {})
    for file in selected:
        queue[file.file_id] = file
    files = list(queue.values())

    results = st.session_state.setdefault("upload-results", {})
    slots = {}
    if files:
        with st.container(key="upload-file-heading"):
            heading, clear = st.columns([3, 1], vertical_alignment="center")
            with heading:
                st.html(f'<div class="sh-up-list-head">선택한 파일<span class="sh-up-count">{len(files)}</span></div>')
            with clear, st.container(horizontal=True, horizontal_alignment="right"):
                st.button("전체 지우기", on_click=clear_upload_files, type="tertiary")
        with st.container(key="upload-file-list"):
            for file in files:
                with st.container(key=f"upload-document-card-{file.file_id}"):
                    icon, details, remove = st.columns([30, 1, 24], vertical_alignment="center")
                    with icon:
                        st.html(format_tile_html(_file_type(file.name), large=True))
                    with details:
                        st.html(f'<div class="sh-up-name">{html.escape(file.name)}</div>')
                        slots[file.file_id] = st.empty()
                    with remove:
                        st.button("×", key=f"remove-{file.file_id}", help="선택 목록에서 제거합니다.",
                                  type="tertiary", on_click=_remove_file, args=(file.file_id,))
                    if file.file_id in results:
                        _show_result(slots[file.file_id], results[file.file_id], file.size)
                    else:
                        slots[file.file_id].html(f'<div class="sh-up-wait">{_format_size(file.size)} · 업로드 대기</div>')

    with st.container(key="upload-info"):
        st.html('<div class="sh-up-info-title">문서 정보</div>'
                '<div class="sh-up-info-sub">목록의 모든 파일에 같은 값이 들어갑니다. '
                '올린 뒤 문서 목록에서 파일별로 바꿀 수 있습니다.</div>')
        # 계열사 관리자는 자사 한 곳뿐이라 바꿀 수 없다. 최종 어드민만 기업을 고른다 (권한은 서비스가 다시 확인한다).
        company_id = st.selectbox("소속 기업", list(names), format_func=names.get,
                                  key="upload-company", disabled=len(names) == 1)
        if len(names) == 1:
            st.html('<div class="sh-up-help">계열사 관리자는 자사 문서만 올릴 수 있습니다.</div>')
        type_column, access_column = st.columns(2, gap="small")
        with type_column:
            doc_type = st.selectbox("문서 유형", list(DOC_TYPE_NAMES), format_func=DOC_TYPE_NAMES.get,
                                    key="upload-doc-type")
        with access_column:
            access_level = st.radio(
                "보안 등급", list(ACCESS_LABELS), index=1, horizontal=True,
                format_func=ACCESS_LABELS.get, key="upload-access",
            )
        st.html(f'<div class="sh-up-note"><span class="sh-up-note-icon"><img src="{_INFO_ICON_URL}" alt=""></span>'
                f'<span>{html.escape(_NOTE_TEXT)}</span></div>')
        # 시안에는 없지만 작성일·목데이터 표시는 색인 결과(기간 필터·시연용 표시)에 쓰이므로 접어 두고 남긴다.
        with st.expander("추가 정보 (선택)"):
            published = st.date_input("작성일 (비워 두면 업로드일을 사용합니다)", value=None)
            is_mock = st.checkbox("직접 만든 목데이터입니다")

    pending = [file for file in files if file.file_id not in results]
    with st.container(key="upload-footer"):
        summary, actions = st.columns([3, 2], vertical_alignment="center")
        with summary:
            show_text(f"{len(files)}개 파일 · {names[company_id]} · {DOC_TYPE_NAMES[doc_type]} · "
                      f"{ACCESS_LABELS[access_level]}로 등록", muted=True)
        with actions, st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            submitted = st.button("업로드", type="primary", disabled=not pending)
    if submitted:
        for file in pending:
            slots[file.file_id].html(upload_status_html(f"{_format_size(file.size)} · 저장하고 색인하는 중", "busy"))
            result = upload_document(file, {
                "company_id": company_id, "doc_type": doc_type,
                "access_level": access_level, "published_date": published,
                "is_mock": is_mock,
            }, user)
            results[file.file_id] = result
            _show_result(slots[file.file_id], result, file.size)


def _show_result(slot, result: dict, size: int) -> None:
    """A-01 파일별 완료·중복·실패 결과를 표시한다."""
    with slot.container():
        if result["index_status"] == "duplicate":
            render_duplicate_notice(result)
        elif result["index_status"] == "done":
            st.html(upload_status_html(f"{_format_size(size)} · 업로드 완료 · 청크 {result['chunk_count']}개", "done"))
        else:
            st.html(upload_status_html(f"{_format_size(size)} · {result['error_message']}", "failed"))
