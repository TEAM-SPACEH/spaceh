"""A-02 문서 목록·색인 상태 UI와 삭제·재색인 요청."""

import html
import logging

import streamlit as st

from app.admin.services.document_service import (
    DEFAULT_PAGE_SIZE,
    delete_document,
    get_document_list,
    request_reindex,
)
from app.common.ui import company_tag_html, empty_state, security_badge_html, show_text

logger = logging.getLogger(__name__)

# 목록 표의 열 너비 비율: 문서, 보안 등급, 색인 상태, 올린 날, 작업
_COLUMN_WIDTHS = [5, 1.4, 1.6, 1.2, 2.4]

_PAGE_KEY = "admin-docs-page"
_FILTER_KEY = "admin-docs-filter-signature"
_NOTICE_KEY = "admin-docs-notice"

# 색인 상태 태그 색: 완료 그린, 실패 빨강, 대기·색인 중 옐로 (보안 등급 태그 색과 같은 규칙)
_STATUS_CLASS = {"done": "sh-pub", "failed": "sh-con", "pending": "sh-int", "indexing": "sh-int"}


def _notice(level: str, text: str) -> None:
    """다음 화면에서 한 번 보여 줄 처리 결과를 남긴다 (처리 뒤 st.rerun()이 화면을 다시 그리기 때문)."""
    st.session_state[_NOTICE_KEY] = (level, text)


def _show_notice() -> None:
    """남겨 둔 처리 결과를 한 번 보여 주고 지운다. 문구는 서비스가 만든 안내라 Markdown 해석 없이 그린다."""
    notice = st.session_state.pop(_NOTICE_KEY, None)
    if not notice:
        return
    level, text = notice
    {"success": st.success, "warning": st.warning}.get(level, st.error)(text.replace("~", "\\~"))


def _document_html(document: dict) -> str:
    """문서 칸: 파일 형식 태그 + 제목 + 기업 태그, 아래 줄에 청크 수·파일명. 모두 html.escape 한다."""
    sub = f"{document['file_name']} · {document['chunk_count']:,}청크" if document["chunk_count"] else document["file_name"]
    return (
        f'<div><span class="sh-tag sh-co">{html.escape(document["file_format"].upper())}</span> '
        f'<b>{html.escape(document["title"])}</b> {company_tag_html(document["company_id"])}</div>'
        f'<div class="sh-muted">{html.escape(sub)}</div>'
    )


def _status_html(document: dict) -> str:
    """색인 상태 태그. 실패면 이유를 마우스를 올리면 보이는 글(title)로 붙인다."""
    css = _STATUS_CLASS.get(document["index_status"], "sh-co")
    tip = f' title="{html.escape(document["error_message"])}"' if document.get("error_message") else ""
    return f'<span class="sh-tag {css}"{tip}>{html.escape(document["status_label"])}</span>'


@st.dialog("문서 삭제")
def _confirm_delete(document: dict, user: dict) -> None:
    """삭제 확인창. 되돌릴 수 없다는 점과 삭제 범위를 알리고, 확인해야만 삭제한다."""
    show_text(document["title"], bold=True)
    show_text("원본 파일, 문서 정보, 검색 색인이 모두 삭제되며 되돌릴 수 없습니다. "
              "이 문서에 대한 열람 권한 요청과 승인 기록도 함께 삭제됩니다.")
    cancel_col, delete_col = st.columns(2)
    if cancel_col.button("취소", key="admin-docs-delete-cancel", use_container_width=True):
        st.rerun()
    if delete_col.button("삭제", key="admin-docs-delete-confirm", type="primary", use_container_width=True):
        with st.spinner("삭제하는 중입니다."):
            result = delete_document(document["doc_id"], user)
        if result["status"] == "deleted":
            _notice("warning" if result["warning"] else "success",
                    "문서를 삭제했습니다." + (f" {result['warning']}" if result["warning"] else ""))
        else:
            _notice("error", result["error_message"])
        st.rerun()


def _run_reindex(document: dict, user: dict) -> None:
    """재색인을 실행하고 결과를 남긴 뒤 화면을 다시 그린다. 임베딩 API를 부르므로 시간이 걸린다."""
    with st.spinner("다시 색인하는 중입니다. 잠시만 기다려 주세요."):
        result = request_reindex(document["doc_id"], user)
    if result["index_status"] == "done":
        _notice("success", f"재색인을 마쳤습니다. 청크 {result['chunk_count']:,}개")
    else:
        _notice("error", result["error_message"] or "재색인에 실패했습니다.")
    st.rerun()


def _render_row(document: dict, user: dict) -> None:
    """문서 한 줄: 문서·보안 등급·색인 상태·올린 날과 재색인·삭제 버튼."""
    cols = st.columns(_COLUMN_WIDTHS, vertical_alignment="center")
    cols[0].html(_document_html(document))
    cols[1].html(security_badge_html(document["access_level"]))
    cols[2].html(_status_html(document))
    with cols[3]:
        show_text(document["created_at"].strftime("%m.%d"), muted=True)
    reindex_col, delete_col = cols[4].columns(2)
    # 버튼을 끄는 것은 안내용이다. 실제로 해도 되는지는 서비스가 다시 확인한다.
    if reindex_col.button("재색인", key=f"admin-docs-reindex-{document['doc_id']}",
                          disabled=not document["can_reindex"], icon=":material/refresh:",
                          help=None if document["can_reindex"] else "원본이 없거나 처리 중인 문서는 다시 색인할 수 없습니다."):
        _run_reindex(document, user)
    if delete_col.button("삭제", key=f"admin-docs-delete-{document['doc_id']}",
                         disabled=not document["can_delete"], icon=":material/delete:",
                         help=None if document["can_delete"] else "색인 중인 문서는 삭제할 수 없습니다."):
        _confirm_delete(document, user)


def _render_pager(page: int, total: int, total_pages: int, shown: int) -> None:
    """"N건 중 a–b"와 이전·다음 버튼. 버튼을 누르면 페이지만 바꾸고 다시 그려서 새 페이지를 읽는다."""
    first = (page - 1) * DEFAULT_PAGE_SIZE + 1
    info_col, prev_col, next_col = st.columns([6, 1, 1])
    with info_col:
        show_text(f"{total:,}건 중 {first:,}–{first + shown - 1:,}", muted=True)
    if prev_col.button("이전", disabled=page <= 1, key="admin-docs-prev"):
        st.session_state[_PAGE_KEY] = page - 1
        st.rerun()
    if next_col.button("다음", disabled=page >= total_pages, key="admin-docs-next"):
        st.session_state[_PAGE_KEY] = page + 1
        st.rerun()


def render_document_list(user: dict, filters: dict) -> None:
    """A-02 관리 가능한 문서와 색인 상태를 표로 보여 주고 삭제·재색인 요청을 받는다.

    user: 로그인 사용자 (권한은 서비스가 다시 확인한다)
    filters: render_document_filters()가 돌려준 선택값
    """
    _show_notice()
    # 필터가 바뀌면 1페이지부터 다시 본다. 그러지 않으면 3페이지에서 검색할 때 빈 페이지가 나온다.
    signature = tuple(sorted(filters.items()))
    if st.session_state.get(_FILTER_KEY) != signature:
        st.session_state[_FILTER_KEY] = signature
        st.session_state[_PAGE_KEY] = 1
    try:
        result = get_document_list(user, filters, st.session_state.get(_PAGE_KEY, 1), DEFAULT_PAGE_SIZE)
    except PermissionError:
        st.warning("관리자 권한이 없거나 변경되었습니다. 다시 로그인해 주세요.")
        return
    except Exception:
        logger.exception("A-02 문서 목록 조회 실패")
        st.error("문서 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    # 서비스가 범위를 벗어난 페이지를 마지막 페이지로 보정했을 수 있다.
    st.session_state[_PAGE_KEY] = result["page"]
    documents = result["documents"]
    if not documents:
        empty_state("조건에 맞는 문서가 없습니다. 검색어나 필터를 바꾸거나 새 문서를 올려 보세요.")
        return
    header = st.columns(_COLUMN_WIDTHS)
    for cell, label in zip(header, ["문서", "보안 등급", "색인 상태", "올린 날", "작업"]):
        with cell:
            show_text(label, bold=True, muted=True)
    for document in documents:
        _render_row(document, user)
    _render_pager(result["page"], result["total"], result["total_pages"], len(documents))
