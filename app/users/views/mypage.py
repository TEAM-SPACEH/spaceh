"""M-02·M-03 마이페이지 화면: 내 프로필과 열람 권한 요청 목록을 보여 준다.

이 화면은 services만 부른다(계층 규칙). 내 정보는 users.user_service, 권한 요청 목록은
permissions.permission_service를 거친다. 메뉴 연결(main.py)은 팀장이 맡는다.
"""

import html
from datetime import datetime

import streamlit as st

from app.auth.session import get_current_user_id
from app.common.ui import company_tag_html, empty_state, page_header, show_text
from app.permissions.services.permission_service import get_access_request_history
from app.users.services.user_service import get_user_info

# 역할 코드 → 화면 이름 (DB에는 영어 코드만 저장, 화면에서 한글로 바꾼다)
_ROLE_LABELS = {
    "employee": "일반 사원",
    "company_admin": "계열사 관리자",
    "super_admin": "최종 관리자",
}

# 요청 상태 코드 → (화면 이름, 공통 테마 배지 클래스). apply_theme의 sh-tag 색을 재사용한다.
_STATUS_BADGES = {
    "pending": ("검토 중", "sh-int"),   # 노랑
    "approved": ("승인", "sh-pub"),      # 초록
    "rejected": ("반려", "sh-con"),      # 빨강
}


def render_mypage() -> None:
    """마이페이지: 프로필 카드 + 열람 권한 요청 목록."""
    user_id = get_current_user_id()
    if user_id is None:
        st.warning("로그인 후 이용할 수 있습니다.")
        return

    info = get_user_info(user_id)
    if info is None:
        st.error("내 정보를 불러오지 못했습니다.")
        return

    page_header("내 정보")
    _render_profile(info)
    st.divider()
    _render_access_requests(user_id)


def _render_profile(info: dict) -> None:
    """프로필 카드: 이름·역할·회사·사원번호. 이름·소속은 사용자가 정한 값이라 show_text로 안전하게 표시."""
    role_label = _ROLE_LABELS.get(info["role"], info["role"])
    with st.container(border=True):
        show_text(info["name"] or info["employee_no"], bold=True)
        # 회사 코드 배지 + 역할 (회사 코드·역할은 고정 값이라 배지로 표시)
        company_code = info["company_id"] or ""
        st.html(f'{company_tag_html(company_code)} <span class="sh-muted">{html.escape(role_label)}</span>')
        show_text(
            f"사원번호 {info['employee_no']} · {info['company_name'] or '소속 없음'}",
            muted=True,
        )


def _render_access_requests(user_id: int) -> None:
    """열람 권한 요청 목록: 문서·회사·요청 시각·상태를 표로 보여 준다."""
    st.subheader("열람 권한 요청")
    requests = get_access_request_history(user_id)
    if not requests:
        empty_state("열람 권한을 요청한 문서가 없습니다.")
        return

    # 표 머리글
    head = st.columns([5, 1, 2, 1])
    for col, label in zip(head, ["문서", "회사", "요청", "상태"]):
        col.caption(label)

    for request in requests:
        doc_col, company_col, time_col, status_col = st.columns([5, 1, 2, 1])
        with doc_col:
            # 문서 제목·사유는 업로더·요청자가 정한 값이라 Markdown 해석 없이(show_text) 보여 준다.
            show_text(request["doc_title"], bold=True)
            if request.get("reason"):
                show_text(f"사유: {request['reason']}", muted=True)
        with company_col:
            st.html(company_tag_html(request["owner_company_code"]))
        with time_col:
            show_text(_format_time(request["created_at"]), muted=True)
        with status_col:
            st.html(_status_badge_html(request["status"]))


def _status_badge_html(status: str) -> str:
    """상태 코드를 한글 배지 HTML로 바꾼다. 모르는 값은 회색으로 코드 그대로 보여 준다."""
    label, css = _STATUS_BADGES.get(status, (status, "sh-co"))
    return f'<span class="sh-tag {css}">{html.escape(label)}</span>'


def _format_time(value: datetime | None) -> str:
    """요청 시각을 'MM.DD HH:MM'으로 보여 준다(없으면 빈 문자열)."""
    return value.strftime("%m.%d %H:%M") if isinstance(value, datetime) else ""
