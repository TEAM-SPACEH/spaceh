"""A-04 감사 로그 화면: render_admin_audit_logs()."""

import logging

import streamlit as st

from app.admin.services.audit_service import (
    DEFAULT_PAGE_SIZE,
    get_audit_filter_options,
    get_audit_log_detail,
    search_audit_logs,
)
from app.admin.views.components.audit_log_detail import render_audit_log_detail
from app.admin.views.components.audit_log_filters import render_audit_log_filters
from app.admin.views.components.audit_log_list import render_audit_log_list
from app.common.ui import page_header

logger = logging.getLogger(__name__)

# 페이지 번호 입력칸과, 필터가 바뀌었는지 알아보기 위한 직전 필터 값을 session_state 에 두는 이름.
_PAGE_KEY = "admin-audit-page"
_FILTER_KEY = "admin-audit-filter-signature"


def render_admin_audit_logs(user: dict) -> None:
    """A-04 조회 권한을 확인하고 감사 로그 필터·목록·상세 화면을 구성한다.

    user: 로그인 사용자. 관리자(계열사 관리자·최종 어드민)만 볼 수 있다.
    권한 판단은 서비스(_resolve_scope)가 하고, 여기서는 PermissionError 를 안내 문구로 바꾼다.
    """
    page_header("감사 로그", "로그인·검색·열람·공유 변경 등 행위를 차단 여부와 함께 확인합니다.")
    try:
        options = get_audit_filter_options(user)
    except PermissionError:
        st.error("감사 로그는 관리자만 조회할 수 있습니다.")
        return
    except Exception:
        logger.exception("A-04 필터 선택지 조회 실패")
        st.error("감사 로그를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    filters = render_audit_log_filters(options)
    # 필터가 바뀌면 1페이지부터 다시 본다. 3페이지를 보다가 조건을 바꾸면 결과가 그 페이지에 없을 수 있다.
    # st.session_state 는 화면을 다시 그려도 유지되는 저장 공간이다. 입력칸(key)을 그리기 전에 값을 넣어야 반영된다.
    signature = repr(sorted(filters.items()))
    if st.session_state.get(_FILTER_KEY) != signature:
        st.session_state[_FILTER_KEY] = signature
        st.session_state[_PAGE_KEY] = 1
    page = int(st.number_input("페이지", min_value=1, step=1, key=_PAGE_KEY))

    try:
        result = search_audit_logs(user, filters, page, DEFAULT_PAGE_SIZE)
    except Exception:
        logger.exception("A-04 감사 로그 조회 실패")
        st.error("감사 로그를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    st.caption(f"총 {result['total_count']}건 · {result['page']} / {result['total_pages']} 페이지")
    log_id = render_audit_log_list(result["logs"])
    if log_id is None:
        return

    try:
        render_audit_log_detail(get_audit_log_detail(log_id, user))
    except LookupError:
        st.warning("선택한 기록을 찾을 수 없습니다.")
    except Exception:
        logger.exception("A-04 감사 로그 상세 조회 실패")
        st.error("상세 정보를 불러오지 못했습니다.")
