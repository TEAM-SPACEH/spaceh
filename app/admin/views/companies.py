"""A-07 계열사 관리 화면: render_admin_companies()."""

import logging

import streamlit as st

from app.admin.services.company_service import get_companies
from app.admin.views.components.company_detail import render_dart_connection
from app.admin.views.components.company_form import render_company_form
from app.admin.views.components.company_list import render_company_list
from app.common.ui import page_header, show_text
from core.constants import ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

# 왼쪽(표·DART 연결)과 오른쪽(계열사 더하기) 너비 비율
_LIST_FORM_WIDTHS = [772, 360]


def render_admin_companies(user: dict) -> None:
    """A-07 최종 어드민 확인 후 계열사 표·DART 연결·계열사 더하기 폼을 보여 준다.

    user: 로그인 사용자. 최종 어드민만 볼 수 있다.
    """
    # 1차 가드(화면 단계). st.stop() 은 이 줄 아래의 화면을 그리지 않고 실행을 멈춘다.
    # 이 가드가 뚫려도 서비스(get_companies·create_company 등)가 권한을 다시 확인한다.
    if user.get("role") != ROLE_SUPER_ADMIN:
        st.error("최종 어드민만 접근할 수 있는 페이지입니다.")
        st.stop()

    show_text("전체 관리", muted=True)
    page_header("계열사", "검색할 회사를 더합니다. 새 회사는 바로 필터와 권한 규칙에 들어갑니다.")

    # 목록은 폼 제출 콜백(화면을 다시 그리기 전에 실행)이 끝난 뒤 읽으므로, 방금 더한 회사가 바로 보인다.
    try:
        companies = get_companies(user)
    except PermissionError:
        st.error("최종 어드민만 접근할 수 있는 페이지입니다.")
        return
    except Exception:
        logger.exception("A-07 계열사 목록 조회 실패")
        st.error("계열사 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    list_col, form_col = st.columns(_LIST_FORM_WIDTHS)
    with list_col:
        render_company_list(companies)
        render_dart_connection(companies, user)
    with form_col:
        render_company_form(user)
