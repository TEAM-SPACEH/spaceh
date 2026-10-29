"""M-01 로그인 화면: render_login().

왼쪽은 서비스 소개(정적), 오른쪽은 사원번호·비밀번호 로그인 폼이다.
로그인 판단과 세션 저장은 auth_service가 맡고, 이 화면은 입력과 결과 표시만 한다.
"""

import logging

import streamlit as st

from app.auth.services import auth_service
from app.common.layout import apply_login_layout, brand_html
from app.common.ui import card, citation_html, company_tag_html, page_header

logger = logging.getLogger(__name__)

# 미등록·비활성·비밀번호 불일치를 구분해 알리면 어떤 사원번호가 있는지 드러나므로 한 문구만 쓴다.
LOGIN_FAILED_MESSAGE = "사원번호 또는 비밀번호가 올바르지 않습니다."
FORM_WIDTH = 360
INTRO_WIDTH = 520
HEADLINE_WIDTH = 460
LOCK_ICON_URL = "app/static/icons/lock.svg"


def render_login() -> None:
    """M-01 사원번호·비밀번호 입력 화면을 그리고, 로그인에 성공하면 메인 화면으로 다시 그린다."""
    # 왼쪽 연회색·오른쪽 흰 패널 틀은 공통 CSS가 그린다 (Figma UI v4 01, #108).
    apply_login_layout()
    intro, form = st.columns(2, gap="small")
    with intro, st.container(key="login-intro", width=INTRO_WIDTH):
        _render_intro()
    with form, st.container(key="login-form", width=FORM_WIDTH):
        _render_login_form()


def _render_intro() -> None:
    """시안 왼쪽 영역. 실제 검색은 하지 않는 예시 화면이다."""
    st.html(brand_html())
    # 제목 한 줄을 좁은 폭에 넣어 시안처럼 "찾고" 뒤에서 줄이 바뀌게 한다.
    with st.container(width=HEADLINE_WIDTH):
        st.header("세 계열사 문서에서 답을 찾고 근거까지 함께 봅니다")
    st.caption("현대경제연구원, 현대무벡스, 현대엘리베이터의 보고서와 공시를 내 권한 안에서만 검색합니다.")

    with card("login-example"):
        st.caption("질문")
        st.markdown("**현대무벡스 스마트팩토리 3분기 수주는?**")
        st.html(
            '<div class="sh-quote">신규 수주 1,284억 원으로 전년 같은 분기보다 18% 늘었습니다.'
            f"{citation_html(1)}</div>"
        )
        st.divider()
        st.html(
            f"<div>{citation_html(1)} {company_tag_html('MVX')} 2025년 3분기 실적 보고서 "
            '<span class="sh-muted">p.7</span></div>'
        )
        st.html(
            f'<div><img class="sh-lock" src="{LOCK_ICON_URL}" width="14" height="14" alt=""> '
            f'{company_tag_html("ELV")} <span class="sh-muted">권한이 없는 문서 1건은 답변에서 제외됨</span></div>'
        )

    st.caption("현대 AI 서비스 개발자 부트캠프 프로젝트 1")


def _render_login_form() -> None:
    page_header("로그인", "회사에서 받은 사원번호로 로그인하세요.")
    with st.form("login_form", border=False):
        employee_no = st.text_input("사원번호", placeholder="MVX-0001", icon=":material/person:")
        password = st.text_input("비밀번호", type="password", icon=":material/key:")
        # 실패 문구를 시안처럼 비밀번호 입력란 바로 아래에 두려고 버튼보다 먼저 자리를 잡는다.
        message = st.empty()
        submitted = st.form_submit_button("로그인", type="primary", width="stretch")
    st.caption("계정이 없거나 비밀번호를 잊었다면 소속 계열사 관리자에게 문의하세요.")

    if not submitted:
        return
    try:
        is_logged_in = auth_service.login(employee_no, password)
    except Exception:
        logger.exception("M-01 로그인 처리 실패")
        message.markdown(":red[:material/error: 로그인 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.]")
        return
    if not is_logged_in:
        message.markdown(f":red[:material/warning: {LOGIN_FAILED_MESSAGE}]")
        return
    st.rerun()
