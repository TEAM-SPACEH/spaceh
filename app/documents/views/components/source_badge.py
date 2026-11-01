"""S-05 출처 배지: 답변 아래에 [번호] 회사 · 파일명 · 위치를 보여 주고 원문 보기로 연결한다."""

# views 파일 = "홀 직원"이에요. 화면에 보여 주고 클릭을 받기만 하고, 권한 판단은 services에 맡겨요.

import streamlit as st

from app.common.ui import citation_html, company_tag_html, empty_state, show_text

# 배지에서 고른 출처를 원문 뷰어에 넘겨줄 세션 이름표. 두 파일이 같은 이름을 써야 해서 상수로 뒀어요.
SELECTED_SOURCE_KEY = "s05_selected_source"


def render_source_badge(sources: list[dict]) -> None:
    """S-05 답변 문장 및 하단에 회사명·파일명·문서 위치 배지를 표시한다."""
    # sources = S-04 generate_answer()의 "sources". 답변에서 실제 인용한 출처만 들어 있어요.
    # 📌 "답변 문장마다" 붙는 배지는 S-04 답변 글자 속 [1] 표시를 바꿔야 해서, 김소은님과 상의 후 추가해요.
    if not sources:
        empty_state("답변에 사용된 출처가 없습니다.")
        return

    for source in sources:
        # 소은님 코드가 원래 번호를 citation_number에 남겨 줘요. 답변 속 [2]와 배지 번호를 맞추려고 그대로 써요.
        number = source.get("citation_number", 0)

        # 출처 하나를 테두리 상자로 묶어요. 버튼을 옆 칸이 아니라 아래에 둔 이유:
        # 답변 영역이 좁으면 옆 칸 버튼 글자가 "원..."처럼 잘려서예요.
        with st.container(border=True):
            # 회사명·파일명은 데이터에서 온 글자라 st.markdown·st.write 대신 공통 UI 함수를 써요.
            # (마크다운 링크·이미지가 몰래 그려지는 것을 막는 팀 규칙)
            st.html(f"{citation_html(number)} {company_tag_html(source['company'])}")
            show_text(f"{source['filename']} · {source['location']}", muted=True)
            # 버튼 글자에 파일명을 넣지 않은 이유: 버튼 글자도 마크다운으로 해석돼서예요.
            # key는 버튼마다 달라야 해서 출처 번호와 청크 ID를 같이 써요.
            if st.button("원문 보기", key=f"s05_badge_{number}_{source.get('chunk_id')}"):
                # Streamlit은 클릭할 때마다 화면 전체를 다시 그려서, 고른 출처를 세션에 기억해 둬요.
                st.session_state[SELECTED_SOURCE_KEY] = source
