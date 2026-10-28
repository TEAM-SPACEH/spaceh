"""A-01 문서 업로드·색인, A-02 문서 목록·삭제·재색인 화면."""

import streamlit as st

from app.admin.views.components.document_upload import clear_upload_files, render_document_upload
from app.common.ui import page_header


def render_admin_documents(user: dict) -> None:
    """A-01 문서 올리기 버튼에서 업로드 모달을 연다."""
    page_header("문서", "보안 등급과 색인 상태를 확인하고 문서를 등록합니다.")
    if st.button("문서 올리기", type="primary", icon=":material/upload:"):
        clear_upload_files()
        render_document_upload(user)
