
"""S-04 근거 기반 AI 답변 카드 UI."""

import html
import re

import streamlit as st

from app.common.ui import citation_html


def render_rag_answer_card(result: dict) -> None:
    answer = result.get("answer", "")
    sources = result.get("sources") or []

    with st.container(border=True, key="s61_rag_card"):

        # 답변이 비어 있는 경우
        if not isinstance(answer, str) or not answer.strip():
            st.info("아직 생성된 답변이 없습니다.")
            return

        # 문서에 답변 근거가 없는 경우
        if answer.strip() == "찾을 수 없음":
            st.info("검색된 문서에서 충분한 답변 근거를 찾지 못했습니다.")
            return

        # HTML 및 Markdown 실행 방지
        safe_answer = html.escape(answer)

        # [1], [2] 등의 인용 번호를 공통 배지로 변환
        formatted_answer = re.sub(
            r"\[(\d+)\]",
            lambda match: citation_html(int(match.group(1))),
            safe_answer,
        )

        # 답변 헤더
        header_html = (
            '<div class="sh-rag-header">'
            '<span class="sh-rag-title">답변</span>'
            f'<span class="sh-rag-meta">근거 문서 {len(sources)}건</span>'
            '</div>'
        )

        # 답변 본문
        body_html = (
            f'<div class="sh-rag-body">{formatted_answer}</div>'
        )

        # 답변 하단 근거 안내
        footer_html = (
            '<div class="sh-rag-footer">'
            '✓ 검색된 문서를 기반으로 생성된 답변입니다.'
            '</div>'
        )

        # 하나의 HTML 블록으로 표시해 불필요한 여백 방지
        st.html(
            header_html + body_html + footer_html
        )
