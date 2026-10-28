"""A-04 감사 로그 화면: render_admin_audit_logs()."""

import logging
from datetime import datetime

import streamlit as st

from app.admin.services.audit_service import (
    DEFAULT_PAGE_SIZE,
    KST,
    export_audit_logs_csv,
    get_audit_filter_options,
    get_audit_log_detail,
    get_audit_scope_name,
    get_audit_summary,
    search_audit_logs,
)
from app.admin.views.components.audit_log_detail import render_audit_log_detail
from app.admin.views.components.audit_log_filters import render_audit_log_filters, show_result_count
from app.admin.views.components.audit_log_list import render_audit_log_list
from app.admin.views.components.audit_log_summary import render_audit_log_summary
from app.common.ui import page_header, show_text
from core.constants import ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

# 페이지 번호 입력칸과, 필터가 바뀌었는지 알아보기 위한 직전 필터 값을 session_state 에 두는 이름.
_PAGE_KEY = "admin-audit-page"
_FILTER_KEY = "admin-audit-filter-signature"

_DESCRIPTION = {
    True: "전체 계열사 사용자의 행동을 모두 기록합니다.",
    False: "우리 회사 사용자의 행동을 모두 기록합니다.",
}


def render_admin_audit_logs(user: dict) -> None:
    """A-04 조회 권한을 확인하고 요약 카드·필터·목록·상세 화면을 구성한다.

    user: 로그인 사용자. 관리자(계열사 관리자·최종 어드민)만 볼 수 있다.
    권한 판단은 서비스(_resolve_scope)가 하고, 여기서는 PermissionError 를 안내 문구로 바꾼다.
    """
    try:
        options = get_audit_filter_options(user)
        scope_name = get_audit_scope_name(user)
        today = datetime.now(KST).date()
        summary = get_audit_summary(user, today)
    except PermissionError:
        st.error("감사 로그는 관리자만 조회할 수 있습니다.")
        return
    except Exception:
        logger.exception("A-04 화면 준비 실패")
        st.error("감사 로그를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    # 제목 줄: 왼쪽 제목, 오른쪽 CSV 버튼. CSV 는 아래 필터 값이 정해진 뒤에 채우므로 칸만 먼저 만든다.
    title_col, csv_col = st.columns([4, 1], vertical_alignment="bottom")
    with title_col:
        # 회사명은 관리자가 입력한 글자일 수 있어 Markdown 해석 없이 보여 준다.
        show_text(f"{scope_name} 관리", muted=True)
        page_header("감사 로그", _DESCRIPTION[user.get("role") == ROLE_SUPER_ADMIN])

    render_audit_log_summary(summary)

    with st.container(border=True):
        filters, count_slot = render_audit_log_filters(options, today)

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

        show_result_count(count_slot, result["total_count"])
        log_id = render_audit_log_list(result["logs"])
        st.caption(f"{result['page']} / {result['total_pages']} 페이지")
        st.caption("감사 로그는 지우거나 고칠 수 없습니다. 차단된 행동도 모두 남습니다.")

    # 내려받기는 눌렀을 때 만들어지고(함수를 넘긴 지연 생성), 그때 내려받기 기록도 감사 로그에 남는다.
    with csv_col:
        st.download_button(
            "CSV 내려받기",
            data=lambda: export_audit_logs_csv(user, filters),
            file_name=f"audit_log_{today:%Y%m%d}.csv",
            mime="text/csv",
            icon=":material/download:",
            key="admin-audit-csv",
        )

    if log_id is None:
        return
    try:
        render_audit_log_detail(get_audit_log_detail(log_id, user))
    except LookupError:
        st.warning("선택한 기록을 찾을 수 없습니다.")
    except Exception:
        logger.exception("A-04 감사 로그 상세 조회 실패")
        st.error("상세 정보를 불러오지 못했습니다.")
