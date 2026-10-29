"""A-01 문서 업로드 모달."""

import streamlit as st

from app.admin.services.document_service import get_upload_companies, upload_document
from app.admin.views.components.duplicate_notice import render_duplicate_notice
from app.common.ui import ACCESS_LABELS, DOC_TYPE_LABELS, company_tag_html, show_text, upload_status_html


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

    st.html('<span class="sh-upload-dialog-marker" hidden></span>')
    st.caption("문서를 선택하고 읽기 권한을 확인해 등록합니다.")
    widget_key = f"document-files-{st.session_state.get('upload-generation', 0)}"
    with st.container(key="upload-picker"):
        selected = st.file_uploader(
            "파일을 여기로 끌어 놓거나 파일을 선택하세요.",
            type=["pdf", "docx", "pptx"], accept_multiple_files=True,
            max_upload_size=20, key=widget_key, label_visibility="collapsed",
            on_change=_queue_files, args=(widget_key,),
        )
        st.caption("PDF · DOCX · PPTX · 파일당 최대 20 MiB · 여러 파일 선택 가능")
    queue = st.session_state.setdefault("upload-files", {})
    for file in selected:
        queue[file.file_id] = file
    files = list(queue.values())
    with st.container(key="upload-file-heading"):
        heading, clear = st.columns([3, 1], vertical_alignment="center")
        with heading:
            show_text(f"선택한 파일 {len(files)}개", bold=True)
        with clear, st.container(horizontal=True, horizontal_alignment="right"):
            st.button("전체 지우기", on_click=clear_upload_files, disabled=not files,
                      type="tertiary")
    results = st.session_state.setdefault("upload-results", {})
    slots = {}
    if files:
        with st.container(height="content" if len(files) == 1 else 160,
                          autoscroll=False, border=False, key="upload-file-list"):
            for file in files:
                with st.container(border=True, key=f"upload-document-card-{file.file_id}"):
                    icon, details, remove = st.columns([1, 8, 1], vertical_alignment="center")
                    with icon:
                        st.html(company_tag_html(file.name.rsplit(".", 1)[-1].upper()))
                    with details:
                        show_text(file.name, bold=True)
                        st.caption(f"{file.size / (1024 * 1024):.2f} MiB")
                    with remove, st.container(horizontal=True, horizontal_alignment="right"):
                        st.button("×", key=f"remove-{file.file_id}", help="선택 목록에서 제거합니다.",
                                  type="tertiary", on_click=_remove_file, args=(file.file_id,))
                    slots[file.file_id] = st.empty()
                    if file.file_id in results:
                        _show_result(slots[file.file_id], results[file.file_id])

    with st.container(key="upload-section-heading"):
        st.markdown("**읽기 권한**")
    names = {company["company_id"]: company["name"] for company in companies}
    company_column, access_column = st.columns(2, gap="small")
    with company_column:
        company_id = st.selectbox("회사", list(names), format_func=names.get,
                                  key="upload-company")
    with access_column:
        access_level = st.selectbox(
            "보안 등급", list(ACCESS_LABELS), index=1,
            format_func=ACCESS_LABELS.get, key="upload-access",
        )
    descriptions = {
        "public": "모든 회사의 직원과 관리자가 읽을 수 있습니다.",
        "internal": "자사 직원·관리자와 최종 어드민이 열람합니다.\n타사는 별도 승인이 필요합니다.",
        "confidential": "자사 관리자와 최종 어드민이 열람합니다.\n그 외에는 별도 승인이 필요합니다.",
    }
    with st.container(key="upload-permission-note"):
        show_text(descriptions[access_level])
    with st.container(key="upload-registration"):
        with st.expander("등록 정보"):
            st.caption("그룹사 공유 OFF · 등록 정보는 선택한 모든 파일에 적용합니다.")
            doc_type = st.selectbox("문서 유형", list(DOC_TYPE_LABELS), format_func=DOC_TYPE_LABELS.get)
            published = st.date_input("작성일 (비워 두면 업로드일을 사용합니다)", value=None)
            is_mock = st.checkbox("직접 만든 목데이터입니다")
            st.caption("문서 제목은 각 파일명에서 확장자를 뺀 이름으로 등록합니다.")

    pending = [file for file in files if file.file_id not in results]
    with st.container(key="upload-footer"):
        st.divider()
        summary, actions = st.columns([3, 2], vertical_alignment="center")
        with summary:
            show_text(f"{len(files)}개 파일 · {names[company_id]} · {ACCESS_LABELS[access_level]}", muted=True)
        with actions, st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            if st.button("닫기"):
                st.rerun()
            submitted = st.button("업로드", type="primary", disabled=not pending)
    if submitted:
        for file in pending:
            slots[file.file_id].html(upload_status_html("문서를 저장하고 색인합니다.", "busy"))
            result = upload_document(file, {
                "company_id": company_id, "doc_type": doc_type,
                "access_level": access_level, "published_date": published,
                "is_mock": is_mock,
            }, user)
            results[file.file_id] = result
            _show_result(slots[file.file_id], result)


def _show_result(slot, result: dict) -> None:
    """A-01 파일별 완료·중복·실패 결과를 표시한다."""
    with slot.container():
        if result["index_status"] == "duplicate":
            render_duplicate_notice(result)
        elif result["index_status"] == "done":
            st.html(upload_status_html(f"색인 완료 · 청크 {result['chunk_count']}개", "done"))
        else:
            st.html(upload_status_html(result["error_message"], "failed"))
