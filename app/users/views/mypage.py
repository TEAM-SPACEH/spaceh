"""M-02·M-03 마이페이지 화면: 내 프로필·비밀번호 바꾸기와 열람 권한 요청 목록을 보여 준다.

이 화면은 services만 부른다(계층 규칙). 내 정보·비밀번호는 users.user_service, 권한 요청 목록은
permissions.permission_service를 거친다. 메뉴 연결(main.py)은 팀장이 맡는다.
"""

import html
import logging
from datetime import datetime

import streamlit as st

from app.auth.session import get_current_user_id
from app.common.ui import company_tag_html, empty_state, page_header, show_text
from app.permissions.services.permission_service import get_access_request_history
from app.users.services.user_service import change_password, get_user_info, validate_password

logger = logging.getLogger(__name__)

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

    try:
        info = get_user_info(user_id)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고, 쉬운 말로 안내하고 자세한 내용은 로그에만 남긴다.
        logger.exception("내 정보 조회 실패")
        st.error("내 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    if info is None:
        st.error("내 정보를 불러오지 못했습니다.")
        return

    page_header("내 정보")
    _render_profile(info)
    # 비밀번호 변경 성공 안내는 폼을 닫고 재실행한 '다음 화면'에서 한 번만 보여 준다(아래 폼 참고).
    if st.session_state.pop("password_changed_flash", False):
        st.success("비밀번호를 변경했습니다.")
    # M-02 비밀번호 바꾸기 폼은 '비밀번호 바꾸기' 버튼을 눌렀을 때만 연다.
    if st.session_state.get("change_password_open"):
        _render_change_password_form(info["user_id"])
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
        # M-02: 누르면 아래에 비밀번호 변경 폼이 열린다.
        if st.button("비밀번호 바꾸기"):
            st.session_state["change_password_open"] = True


def _render_change_password_form(user_id: int) -> None:
    """M-02 현재 비밀번호 확인 → 새 비밀번호 검증 → 변경. user_service에 맡기고 결과만 안내한다."""
    # clear_on_submit=True: 제출하면 입력칸을 비운다(비밀번호를 화면에 남기지 않는다. 기본값은 False).
    with st.form("change_password_form", clear_on_submit=True):
        st.markdown("**비밀번호 바꾸기**")
        current = st.text_input("현재 비밀번호", type="password")
        new = st.text_input("새 비밀번호 (8~20자, 영문·숫자 포함, 공백 없음)", type="password")
        confirm = st.text_input("새 비밀번호 확인", type="password")
        submitted = st.form_submit_button("변경")

    if not submitted:
        return

    # 서비스를 부르기 전에 화면에서 먼저 거른다. 실패 원인마다 메시지를 나눠 안내한다.
    # 1) 새 비밀번호와 확인이 다름
    if new != confirm:
        st.error("새 비밀번호와 확인이 일치하지 않습니다.")
        return
    # 2) 새 비밀번호 규칙 위반. 먼저 여기서 걸러야 아래 서비스 False를 '현재 비밀번호 불일치'로 좁힐 수 있다.
    if not validate_password(new):
        st.error("새 비밀번호가 규칙(8~20자, 영문·숫자 포함, 공백 없음)에 맞지 않습니다.")
        return

    try:
        # 서비스도 같은 검증을 다시 한다(화면 검사를 통과해도 서비스가 최종 판단 — 검증은 유지한다).
        changed = change_password(user_id, current, new)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고 쉬운 말로 안내한다(스택 트레이스는 로그에만).
        logger.exception("비밀번호 변경 실패")
        st.error("비밀번호 변경 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if changed:
        # 폼을 즉시 닫고(입력도 비움) 성공 안내는 다음 재실행 화면에서 한 번 보여 준다.
        st.session_state.pop("change_password_open", None)
        st.session_state["password_changed_flash"] = True
        st.rerun()
    else:
        # 위에서 규칙 위반은 이미 걸렀으므로, 서비스가 False면 현재 비밀번호 불일치다.
        st.error("현재 비밀번호가 올바르지 않습니다.")


def _render_access_requests(user_id: int) -> None:
    """열람 권한 요청 목록: 문서·회사·요청 시각·상태를 표로 보여 준다."""
    st.subheader("열람 권한 요청")
    try:
        requests = get_access_request_history(user_id)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고, 쉬운 말로 안내하고 자세한 내용은 로그에만 남긴다.
        logger.exception("열람 권한 요청 목록 조회 실패")
        st.error("열람 권한 요청 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
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
