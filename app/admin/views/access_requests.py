"""A-05 권한 요청 승인·반려 화면."""

import streamlit as st

from app.admin.views.components.access_request_list import render_access_requests
from app.common.ui import page_header
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN


def render_admin_permissions(user: dict) -> None:
    """A-05 관리자의 열람 요청 상태 필터와 요청 목록을 표시한다."""
    if user.get("role") not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        st.error("관리자만 접근할 수 있는 페이지입니다.")
        return
    page_header("열람 권한 요청", "문서 열람 요청을 확인하고 승인하거나 반려합니다.")
    status = st.selectbox(
        "요청 상태", ["pending", "approved", "rejected", ""],
        format_func=lambda value: {"pending": "대기", "approved": "승인", "rejected": "반려", "": "전체"}[value],
        key="access_request_status",
    )
    render_access_requests(user, {"status": status})
