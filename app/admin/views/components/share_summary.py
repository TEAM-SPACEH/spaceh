"""A-03 그룹사 공유 요약 카드 UI: render_share_summary()."""

import streamlit as st

from app.common.ui import show_text


def render_share_summary(summary: dict) -> None:
    """A-03 그룹사 공유 중·공유 꺼짐·공유 불가(기밀) 문서 수를 카드 3개로 보여 준다.

    summary: get_share_summary() 결과. 숫자는 모두 관리 범위 안의 문서 기준이다.
    색·글꼴은 테마가 정하므로 st.metric 의 기본 모양을 쓴다.
    """
    shared_col, unshared_col, confidential_col = st.columns(3)
    with shared_col, st.container(border=True):
        st.metric(":green[●] 그룹사 공유 중", f"{summary['shared']:,}")
        show_text(f"사내 문서 {summary['internal_total']:,}건 중", muted=True)
    with unshared_col, st.container(border=True):
        st.metric("공유 꺼짐 (사내)", f"{summary['unshared']:,}")
        show_text("다른 계열사에는 보이지 않습니다.", muted=True)
    with confidential_col, st.container(border=True):
        st.metric(":red[●] 공유 불가 (기밀)", f"{summary['confidential']:,}")
        show_text("승인받은 사람만 볼 수 있습니다.", muted=True)
