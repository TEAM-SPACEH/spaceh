"""A-05 권한 요청 승인·반려 화면 (Figma 09): 왼쪽 요청 목록(대기·승인·반려 탭)과 오른쪽 선택한 요청의 상세·처리."""

import html
import logging

import streamlit as st

from app.admin.services.access_service import get_share_scope_name
from app.admin.views.components.access_request_detail import render_access_request_detail
from app.admin.views.components.access_request_list import render_access_request_list
from app.common.ui import empty_state
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

# [문서 보기]로 원문 뷰어를 연 상태. 다른 화면의 뷰어와 헷갈리지 않게 이 화면이 직접 표시를 남긴다.
VIEWER_FLAG_KEY = "ar_viewing_document"
# 처리 결과 안내를 다음 화면에서 한 번 보여 준다 (처리 뒤 st.rerun()이 화면을 다시 그리기 때문).
NOTICE_KEY = "access_review_notice"


def render_admin_permissions(user: dict) -> None:
    """A-05 관리자의 열람 요청 목록과 선택한 요청의 상세·승인·반려 화면을 표시한다."""
    if user.get("role") not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        st.error("관리자만 접근할 수 있는 페이지입니다.")
        return

    # [문서 보기]를 눌렀으면 요청 화면 대신 원문 뷰어를 보여 준다. 뷰어의 [돌아가기]가 고른 출처를 지우면 목록으로 돌아온다.
    if st.session_state.get(VIEWER_FLAG_KEY) and st.session_state.get(SELECTED_SOURCE_KEY):
        render_selected_source(user, back_label="요청으로 돌아가기")
        return
    st.session_state.pop(VIEWER_FLAG_KEY, None)

    try:
        scope_name = get_share_scope_name(user)
    except PermissionError as exc:
        st.error(str(exc))
        return
    except Exception:
        logger.exception("A-05 관리 범위 조회 실패")
        st.error("화면을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    # 회사명은 관리자가 입력한 값일 수 있어 escape한 HTML로 그린다.
    st.html(
        f'<div class="sh-r-crumb">{html.escape(scope_name)} 관리</div>'
        '<div class="sh-r-title">열람 권한 요청</div>'
        '<div class="sh-r-desc">다른 계열사 사용자가 우리 회사 문서를 보려고 보낸 요청입니다.</div>'
    )
    notice = st.session_state.pop(NOTICE_KEY, None)
    if notice:
        st.success(notice)

    list_col, detail_col = st.columns([420, 654], gap="medium")
    with list_col:
        selected = render_access_request_list(user)
    with detail_col:
        if selected is None:
            with st.container(key="ar_empty_detail"):
                empty_state("처리할 요청을 왼쪽 목록에서 선택해 주세요.")
        else:
            render_access_request_detail(user, selected)
