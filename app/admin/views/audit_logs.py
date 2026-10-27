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

logger = logging.getLogger(__name__)


def render_admin_audit_logs(user: dict) -> None:
    """A-04 조회 권한을 확인하고 감사 로그 필터·목록·상세 화면을 구성한다.

    user: 로그인 사용자. 관리자(계열사 관리자·최종 어드민)만 볼 수 있다.
    권한 판단은 서비스(_resolve_scope)가 하고, 여기서는 PermissionError 를 안내 문구로 바꾼다.
    """
    st.title("감사 로그")
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
    page = int(st.number_input("페이지", min_value=1, value=1, step=1))

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
