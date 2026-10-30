"""A-04 감사 로그 요약 카드 UI: render_audit_log_summary()."""

import streamlit as st

from app.admin.services.audit_service import HOURLY_START
from app.common.ui import card, show_text


def render_audit_log_summary(summary: dict) -> None:
    """A-04 오늘 기록·차단된 접근·원문 내려받기·시간대별 기록을 카드 한 줄로 보여 준다.

    summary: get_audit_summary() 결과. 숫자는 모두 관리자 조회 범위 안의 오늘 로그 기준이다.
    색·글꼴은 테마가 정하므로 st.metric 의 기본 모양을 쓴다.
    """
    with card("audit-summary"):
        today_col, blocked_col, download_col, hourly_col = st.columns(4)

        with today_col:
            gap = summary["today_count"] - summary["yesterday_count"]
            if gap > 0:
                compare = f"어제보다 {gap:,}건 많음"
            elif gap < 0:
                compare = f"어제보다 {-gap:,}건 적음"
            else:
                compare = "어제와 같음"
            # delta 는 숫자 부호에 따라 화살표·색이 붙는데, 여기서는 좋고 나쁨의 뜻이 없어 끈다.
            st.metric("오늘 기록", f"{summary['today_count']:,}", delta=compare, delta_color="off", delta_arrow="off")

        with blocked_col:
            st.metric(":red[●] 차단된 접근", f"{summary['blocked_count']:,}")
            # 사유는 다른 기능이 적은 글자라 Markdown 으로 해석되지 않게 show_text 로 보여 준다.
            reasons = ", ".join(f"{reason} {count:,}" for reason, count in summary["blocked_reasons"])
            show_text(reasons or "오늘 차단된 접근이 없습니다.", muted=True)

        with download_col:
            st.metric("원문 내려받기", f"{summary['download_count']:,}")
            if summary["download_count"] == 0:
                note = "오늘 내려받기가 없습니다."
            elif summary["blocked_download_count"] == 0:
                note = "모두 권한 확인 통과"
            else:
                note = f"{summary['blocked_download_count']:,}건 차단"
            show_text(note, muted=True)

        with hourly_col:
            hourly = summary["hourly"]
            peak = max(hourly)
            # 막대 그래프는 st.metric 의 chart_data 로 그린다 (추가 패키지 없이 Streamlit 기본 기능).
            st.metric(
                "시간대별 기록",
                f"{hourly.index(peak) + HOURLY_START:02d}시 최다" if peak else "기록 없음",
                chart_data=hourly,
                chart_type="bar",
            )
            show_text(f"{HOURLY_START:02d}시 ~ {HOURLY_START + len(hourly) - 1:02d}시", muted=True)
