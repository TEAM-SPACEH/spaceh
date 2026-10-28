"""A-05 자사 소유 문서 열람 요청 목록 UI."""

import logging

import streamlit as st

from app.admin.services.access_service import get_access_request_list
from app.admin.views.components.access_request_actions import render_access_request_actions
from app.common.ui import empty_state, show_text

logger = logging.getLogger(__name__)


def render_request_status(request_id: int, status: str) -> None:
    """A-05 요청 번호와 대기·승인·반려 상태를 표시한다."""
    label = {"pending": "대기", "approved": "승인", "rejected": "반려"}.get(status, "알 수 없음")
    show_text(f"요청 #{request_id} · {label}", muted=True)


def render_access_requests(user: dict, filters: dict) -> None:
    """A-05 관리자 범위의 요청자·사유·처리 상태와 페이지 이동을 표시한다."""
    page_key = f"access_request_page_{user['id']}_{filters.get('status', '')}"
    page = st.session_state.get(page_key, 1)
    try:
        result = get_access_request_list(user, filters, page, 20)
    except PermissionError as exc:
        st.error(str(exc))
        return
    except Exception:
        logger.exception("A-05 열람 요청 목록 조회 실패")
        st.error("열람 요청을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    notice = st.session_state.pop("access_review_notice", None)
    if notice:
        st.success(notice)
    show_text(f"전체 {result['total_count']}건", muted=True)
    if not result["requests"]:
        empty_state("해당 상태의 열람 요청이 없습니다.")
        return
    for request in result["requests"]:
        with st.container(border=True):
            render_request_status(request["id"], request["status"])
            show_text(request["title"], bold=True)
            show_text(f"{request['requester_name']} · {request['employee_no']} · {request['company_id']}")
            show_text(f"신청일: {request['created_at']}", muted=True)
            show_text(f"요청 사유: {request['reason']}")
            if request["status"] == "pending":
                render_access_request_actions(request["id"], user)
            else:
                show_text(f"처리일: {request['reviewed_at']}", muted=True)
                if request["review_comment"]:
                    show_text(f"반려 사유: {request['review_comment']}")
    page = result["page"]
    previous, current, following = st.columns([1, 2, 1])
    if previous.button("이전", disabled=page <= 1, key="access_request_previous"):
        st.session_state[page_key] = page - 1
        st.rerun()
    with current:
        show_text(f"{page} / {result['total_pages']} 페이지", muted=True)
    if following.button("다음", disabled=page >= result["total_pages"], key="access_request_next"):
        st.session_state[page_key] = page + 1
        st.rerun()
