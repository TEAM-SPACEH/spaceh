"""spaceH Streamlit 진입점. 저장소 루트에서 `streamlit run main.py`로 실행한다."""

import streamlit as st

from app.common.ui import apply_theme

st.set_page_config(page_title="spaceH", layout="wide")
apply_theme()


def home() -> None:
    st.title("spaceH")
    st.caption("계열사 통합 문서 검색 플랫폼 — 화면은 각 패키지의 views에서 추가한다.")


# 로그인 확인·역할별 메뉴는 M-01 구현 때 여기에 붙인다
st.navigation([st.Page(home, title="홈")]).run()
