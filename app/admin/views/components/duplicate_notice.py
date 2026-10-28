"""A-01·A-02 중복 문서 경고 UI."""

import streamlit as st

from app.common.ui import show_text


def render_duplicate_notice(duplicate_result: dict) -> None:
    """A-01 동일 기업의 기존 문서를 안내하고 자동 덮어쓰기를 하지 않는다."""
    st.warning("이미 등록된 파일입니다. 기존 문서를 확인해 주세요.")
    document = duplicate_result.get("document") or {}
    show_text(document.get("title", ""))
    show_text(f"문서 ID: {document.get('doc_id', '')} / 상태: {document.get('index_status', '')}")
