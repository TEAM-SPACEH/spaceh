"""AI 답변 인용 출처 패널."""

import html

import streamlit as st

from app.common.ui import card, citation_html, company_tag_html
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY


def render_rag_source_panel(sources: list[dict], key_prefix: str = "s61_source") -> None:
    """출처를 기업별 카드로 표시합니다.

    key_prefix: [원문 보기] 버튼 key 앞부분. 한 화면에 패널을 여러 개 그릴 때
        (R-02 보고서 섹션별 출처 등) 패널마다 다르게 넘겨 key 중복을 막는다.
    """

    st.html('<div class="sh-s61-source-title">출처<span>회사별로 나눠 보기</span></div>')

    if not sources:
        # Figma 14: 출처 칸에 빈 카드로 근거가 없음을 알린다.
        with card(f"{key_prefix}-empty"):
            st.html(
                '<div class="sh-src-empty-title">근거로 쓴 문서가 없습니다.</div>'
                '<div class="sh-src-empty-note">검색 결과가 있어도 질문과 관련이 낮으면 답변 근거로 쓰지 않습니다.</div>'
            )
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

        with card(f"{key_prefix}-{group_index}"):
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

                # 번호, 문서명 및 페이지. Figma 02처럼 오른쪽 끝에 링크 모양 [원문] 버튼을 둔다.
                entry_col, open_col = st.columns([4, 1], vertical_alignment="top", gap="small")

                with entry_col:
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

                with open_col:
                    if st.button(
                        "원문",
                        key=f"{key_prefix}_{group_index}_{index}",
                        type="tertiary",
                        icon=":material/visibility:",
                    ):
                        # 기존 S-05 원문 뷰어와 동일한 세션 키 사용
                        st.session_state[SELECTED_SOURCE_KEY] = source
