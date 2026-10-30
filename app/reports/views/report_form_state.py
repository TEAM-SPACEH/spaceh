"""R-01 새 보고서 폼이 쓰는 세션 칸 이름과 기본값, 저장된 보고서의 조건으로 폼을 채우는 함수.

폼(report_form)과 보고서 보기(report_view)가 서로를 부르면 순환 import가 되어, 둘이 함께 쓰는 것만 여기 둔다.
"""

from datetime import date

import streamlit as st

from app.reports.models.report_models import ReportRequest, ReportTemplate

# 화면이 쓰는 세션 칸 이름
TOPIC_KEY = "r01_topic"
COMPANIES_KEY = "r01_companies"
START_KEY = "r01_start"
END_KEY = "r01_end"
TEMPLATE_KEY = "r01_template"        # 고른 양식 (ReportTemplate 값)
REQUEST_KEY = "r01_request"          # 마지막으로 만든 ReportRequest

# 처음 보이는 기간 (Figma 예시 값). 목데이터가 이 기간의 문서라서 같은 값으로 시작해요.
DEFAULT_START = date(2025, 7, 1)
DEFAULT_END = date(2025, 10, 31)

# 보고서 보기 주소의 조회 값 이름 (/reports?report_id=1)
REPORT_ID_PARAM = "report_id"


def prefill_form(request: ReportRequest) -> None:
    """[다시 만들기]: 폼 입력칸을 저장된 보고서의 조건으로 채운다. 버튼 콜백에서 불러야 화면을 다시 그리기 전에 적용된다."""
    st.session_state[TOPIC_KEY] = request.topic
    st.session_state[COMPANIES_KEY] = list(request.company_ids)
    st.session_state[START_KEY] = request.start_date
    st.session_state[END_KEY] = request.end_date
    st.session_state[TEMPLATE_KEY] = ReportTemplate(request.template).value
