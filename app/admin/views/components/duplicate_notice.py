"""A-01·A-02 중복 문서 경고 UI."""

import html

import streamlit as st

from app.common.ui import upload_status_html


def render_duplicate_notice(duplicate_result: dict) -> None:
    """A-01 동일 기업의 기존 문서를 안내하고 자동 덮어쓰기를 하지 않는다."""
    st.html(upload_status_html("이미 등록된 파일입니다. 기존 문서를 확인해 주세요.", "duplicate"))
    document = duplicate_result.get("document") or {}
    # 제목·ID는 DB 값이라 escape한다 (Markdown·HTML로 해석하지 않는다).
    st.html(f'<div class="sh-up-dup">{html.escape(document.get("title", ""))} · '
            f'문서 ID {html.escape(str(document.get("doc_id", "")))} · 상태 {html.escape(str(document.get("index_status", "")))}</div>')
