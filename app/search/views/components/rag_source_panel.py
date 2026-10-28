"""AI 답변 인용 출처 패널."""

import html

import streamlit as st

from app.common.ui import citation_html, company_tag_html, empty_state
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY

def render_rag_source_panel(sources: list[dict]) -> None:
    """출처를 기업별 카드로 표시합니다."""

    st.html('<div class="sh-s61-source-title">출처</div>')

    if not sources:
        empty_state("표시할 인용 출처가 없습니다.")
        return

    # 기업별 출처 묶기 (입력 순서 유지)
    grouped = {}

    for source in sources:
        company = str(source.get("company") or "기업 정보 없음")
        company_id = str(source.get("company_id") or "").strip()

        # 회사 코드가 있으면 코드 기준으로 그룹화
        # 코드가 없는 기존 데이터는 회사명 기준으로 그룹화
        group_key = (
            ("id", company_id)
            if company_id
            else ("name", company)
        )

        if group_key not in grouped:
            grouped[group_key] = {
                "company": company,
                "company_id": company_id,
                "sources": [],
            }

        grouped[group_key]["sources"].append(source)

    # 기업별 카드 출력
    for group_index, group in enumerate(grouped.values()):
        company = group["company"]
        company_id = group["company_id"]
        company_sources = group["sources"]
        company_badge = (
            company_tag_html(company_id)
            if company_id
            else ""
        )

        with st.container(border=True):
            # 기업명 및 출처 건수
            st.html(
                '<div class="sh-s61-source-header">'
                f'{company_badge}'
                f'<strong>{html.escape(company)}</strong>'
                f'<span class="sh-s61-source-count">'
                f'{len(company_sources)}건'
                '</span></div>'
            )

            for index, source in enumerate(company_sources):
                number = source.get("citation_number", 0)
                filename = str(source.get("filename") or "문서명 없음")
                location = str(source.get("location") or "")

                # 번호, 문서명 및 페이지
                st.html(
                    '<div class="sh-s61-source-entry">'
                    f'{citation_html(number)}'
                    '<span class="sh-s61-source-file">'
                    f'{html.escape(filename)}'
                    '</span></div>'
                    '<div class="sh-s61-source-location">'
                    f'{html.escape(location)}'
                    '</div>'
                )

                if st.button(
                    "원문 보기",
                    key=f"s61_source_{group_index}_{index}",
                ):
                    # 기존 S-05 원문 뷰어와 동일한 세션 키 사용
                    st.session_state[SELECTED_SOURCE_KEY] = source
