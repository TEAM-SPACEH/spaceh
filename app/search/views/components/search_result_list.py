"""통합 검색 결과 목록 UI"""

import html

import streamlit as st

from app.common.ui import company_tag_html, security_badge_html


def render_search_result_list(chunks: list[dict]) -> None:
    """검색 청크를 문서별로 묶어 Figma 스타일 목록으로 표시합니다."""

    documents = {}

    for index, chunk in enumerate(chunks):
        metadata = chunk.get("metadata") or {}
        doc_id = (
            chunk.get("doc_id")
            or metadata.get("doc_id")
            or chunk.get("chunk_id")
            or f"unknown-{index}"
        )

        if doc_id not in documents:
            documents[doc_id] = {
                "metadata": metadata,
                "text": str(chunk.get("text") or ""),
            }

    rows = []

    for doc in documents.values():
        meta = doc["metadata"]

        title = str(
            meta.get("title")
            or meta.get("file_name")
            or "제목 없는 문서"
        )

        filename = str(meta.get("file_name") or "")
        file_format = str(meta.get("file_format") or "").upper()

        if meta.get("source_type") == "dart":
            file_format = "DART"
        elif not file_format and "." in filename:
            file_format = filename.rsplit(".", 1)[-1].upper()

        if not file_format:
            file_format = "FILE"

        company_id = str(meta.get("company_id") or "")
        access_level = str(meta.get("access_level") or "")

        preview = " ".join(doc["text"].split())[:120]
        published_date = str(meta.get("published_date") or "")

        if len(published_date) == 8 and published_date.isdigit():
            published_date = (
                f"{published_date[:4]}."
                f"{published_date[4:6]}."
                f"{published_date[6:]}"
            )

        badges = ""

        if company_id:
            badges += company_tag_html(company_id)

        if access_level:
            badges += security_badge_html(access_level)

        rows.append(
            '<div class="sh-s61-result-row">'
            # 형식별 타일 색은 공통 CSS가 정한다 (PDF 빨강, DART 초록, DOC·DOCX 파랑, PPT·PPTX 주황)
            f'<span class="sh-s61-result-type sh-type-{html.escape(file_format.lower())}">'
            f'{html.escape(file_format)}</span>'
            '<div class="sh-s61-result-content">'
            '<div class="sh-s61-result-name">'
            f'{html.escape(title)} {badges}'
            '</div>'
            f'<div class="sh-s61-result-preview">{html.escape(preview)}</div>'
            '</div>'
            f'<span class="sh-s61-result-date">{html.escape(published_date)}</span>'
            '</div>'
        )

    st.html(
        '<div class="sh-s61-results">'
        '<div class="sh-s61-results-header">'
        '<strong>검색 결과</strong>'
        f'<span>{len(documents)}건</span>'
        '<span class="sh-s61-results-sort">관련도순</span>'
        '</div>'
        + "".join(rows)
        + '</div>'
    )
