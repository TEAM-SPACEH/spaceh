"""A-01 문서 업로드·색인, A-02 문서 목록·삭제·재색인, A-03 그룹사 공유 화면."""

import streamlit as st

from app.admin.services.document_service import get_document_filter_options, get_upload_companies
from app.admin.views.components.document_filters import render_document_filters
from app.admin.views.components.document_list import render_document_list
from app.admin.views.components.document_upload import clear_upload_files, render_document_upload
from app.admin.views.sharing import render_admin_sharing
from app.common.ui import page_header


def render_admin_documents(user: dict) -> None:
    """A-01·A-02 관리자 권한을 확인한 뒤 업로드 버튼과 필터·문서 목록을 구성한다. 공유 설정(A-03)은 탭으로 둔다."""
    page_header("문서", "보안 등급과 색인 상태를 확인하고 문서를 등록합니다.")
    try:
        companies = get_upload_companies(user)
    except PermissionError:
        st.warning("관리자 권한이 없거나 변경되었습니다. 다시 로그인해 주세요.")
        return
    except Exception:
        st.error("관리자 권한을 확인할 수 없습니다. DB 연결을 확인해 주세요.")
        return
    list_tab, share_tab = st.tabs(["문서 목록", "그룹사 공유"])
    with list_tab:
        if st.button("문서 올리기", type="primary", icon=":material/upload:"):
            clear_upload_files()
            render_document_upload(user)
        options = get_document_filter_options()
        filters = render_document_filters(
            companies, options["doc_types"], options["security_levels"], options["index_statuses"])
        render_document_list(user, filters)
    with share_tab:
        render_admin_sharing(user)
