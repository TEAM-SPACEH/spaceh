"""A-01 문서 업로드·색인, A-02 문서 목록·삭제·재색인 화면."""

import streamlit as st

from app.admin.services.document_service import get_upload_companies
from app.admin.views.components.document_upload import clear_upload_files, render_document_upload
from app.common.ui import page_header


def render_admin_documents(user: dict) -> None:
    """A-01 현재 관리자 권한을 확인한 뒤 문서 업로드 모달을 제공한다."""
    page_header("문서", "보안 등급과 색인 상태를 확인하고 문서를 등록합니다.")
    try:
        get_upload_companies(user)
    except PermissionError:
        st.warning("관리자 권한이 없거나 변경되었습니다. 다시 로그인해 주세요.")
        return
    except Exception:
        st.error("관리자 권한을 확인할 수 없습니다. DB 연결을 확인해 주세요.")
        return
    if st.button("문서 올리기", type="primary", icon=":material/upload:"):
        clear_upload_files()
        render_document_upload(user)
