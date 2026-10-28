"""A-04 감사 로그 상세 UI: render_audit_log_detail()."""

import streamlit as st


def render_audit_log_detail(log: dict) -> None:
    """A-04 감사 로그 1건의 상세(대상·검색 조건·관련 문서·차단 사유)를 보여 준다.

    log: get_audit_log_detail() 결과
    """
    # 사용자가 입력했거나 외부에서 온 값(사원번호·차단 사유·검색어·대상 ID)은 st.write·st.error·
    # st.markdown 으로 그리면 Markdown 으로 해석된다. 예) "[링크](http://...)", "**굵게**", 이미지 태그.
    # 감사 로그는 로그인 실패 때 입력된 사원번호처럼 신뢰할 수 없는 값을 그대로 담으므로,
    # 값이 들어가는 줄은 해석 없이 글자 그대로 보여 주는 st.text 로 출력한다.
    # 고정 문구(제목·"차단됨"·"정상 처리됨")와 상태 표시는 기존 방식을 유지한다.
    st.subheader(f"기록 #{log['log_id']}")
    st.text(
        f"{log['created_at']} · {log.get('employee_no') or '(알 수 없음)'}"
        f" ({log.get('role') or '-'} / {log.get('company_code') or '-'})"
    )
    st.text(
        f"행위: {log['action_type']} · 대상: {log.get('target_type') or '-'} {log.get('target_id') or ''}"
    )

    if log["blocked"]:
        st.error("차단됨")
        st.text(f"차단 사유: {log.get('block_reason') or '사유 없음'}")
    else:
        st.success("정상 처리됨")

    if log.get("query"):
        st.text(f"검색어·질문: {log['query']}")
    if log.get("result_count") is not None:
        st.text(f"결과 건수: {log['result_count']}")

    # 값이 있는 JSON 항목만 보여 준다. 키 이름을 화면용 한글로 바꿔 둔다.
    details = {
        "적용 필터": log.get("filters"),
        "결과·근거 문서 ID": log.get("doc_ids"),
        "결과 문서의 회사": log.get("doc_companies"),
        "부가 정보": log.get("context_detail"),
    }
    for title, value in details.items():
        if value:
            st.caption(title)
            st.json(value)
