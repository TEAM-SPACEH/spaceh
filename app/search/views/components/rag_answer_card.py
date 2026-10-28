
"""S-04 근거 기반 AI 답변 카드 UI."""

import html
import re

import streamlit as st

from app.common.ui import citation_html, empty_state
from app.search.services.rag_service import is_no_answer


def render_rag_answer_card(result: dict) -> None:
    answer = result.get("answer", "")
    sources = result.get("sources") or []

    with st.container(border=True, key="s61_rag_card"):

        # 답변이 비어 있는 경우
        if not isinstance(answer, str) or not answer.strip():
            empty_state("아직 생성된 답변이 없습니다.")
            return

        # 문서에 답변 근거가 없는 경우
        if is_no_answer(answer):
            empty_state("검색된 문서에서 충분한 답변 근거를 찾지 못했습니다.")
            return

        # HTML 및 Markdown 실행 방지
        safe_answer = html.escape(answer)

        # [1], [2] 등의 인용 번호를 공통 배지로 변환
        formatted_answer = re.sub(
            r"\[(\d+)\]",
            lambda match: citation_html(int(match.group(1))),
            safe_answer,
        )

        
        # 클립보드에 복사할 원본 답변
        # HTML 속성에 넣기 전에 특수문자 이스케이프
        copy_payload = html.escape(answer.strip(), quote=True)

        header_html = (
            '<div class="sh-rag-header">'
            '<span class="sh-rag-title">답변</span>'
            f'<span class="sh-rag-meta">근거 문서 {len(sources)}건</span>'
            f'<button type="button" id="s61-copy-answer" '
            f'class="sh-rag-copy" data-copy="{copy_payload}">'
            '⧉ 복사'
            '</button>'
            '</div>'
        )

        body_html = (
            f'<div class="sh-rag-body">{formatted_answer}</div>'
        )

        footer_html = (
            '<div class="sh-rag-footer">'
            '✓ 검색된 문서를 기반으로 생성된 답변입니다.'
            '</div>'
        )

        # 사용자 브라우저에서 클립보드 복사
        copy_script = """
        <script>
        (() => {
            const button = document.getElementById("s61-copy-answer");
            if (!button) return;

            button.addEventListener("click", async () => {
                try {
                    await navigator.clipboard.writeText(
                        button.dataset.copy || ""
                    );
                    button.textContent = "✓ 복사됨";
                } catch (error) {
                    button.textContent = "복사 실패";
                }
            });
        })();
        </script>
        """

        st.html(
            header_html + body_html + footer_html + copy_script,
            unsafe_allow_javascript=True,
        )
