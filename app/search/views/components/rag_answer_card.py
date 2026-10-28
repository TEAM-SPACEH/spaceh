
"""S-04 근거 기반 AI 답변 카드 UI."""

import html
import re

import streamlit as st

from app.common.ui import citation_html


def render_rag_answer_card(result: dict) -> None:
    """AI 답변과 인용 번호를 화면에 표시합니다."""

    answer = result.get("answer", "")
    sources = result.get("sources") or []

    with st.container(border=True):
        st.subheader("답변")

        # 답변이 없는 경우
        if not isinstance(answer, str) or not answer.strip():
            st.info("아직 생성된 답변이 없습니다.")
            return

        # 근거를 찾지 못한 경우
        if answer.strip() == "찾을 수 없음":
            st.info("검색된 문서에서 충분한 답변 근거를 찾지 못했습니다.")
            return

        # 답변에 포함된 HTML 특수문자 이스케이프
        safe_answer = html.escape(answer)

        # [1], [2] 등 출처 번호를 공통 배지 스타일로 변환
        formatted_answer = re.sub(
            r"\[(\d+)\]",
            lambda match: citation_html(int(match.group(1))),
            safe_answer,
        )

        # 문서 내용의 Markdown/HTML 실행을 방지하면서 표시
        st.html(
            f'<div class="sh-text">{formatted_answer}</div>'
        )

        # 인용 출처 개수
        st.caption(f"인용 출처 {len(sources)}건")
