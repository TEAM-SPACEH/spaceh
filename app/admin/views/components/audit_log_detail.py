"""A-04 감사 로그 상세 UI: render_audit_log_detail()."""

import streamlit as st


def render_audit_log_detail(log: dict) -> None:
    """A-04 감사 로그 1건의 상세(대상·검색 조건·관련 문서·차단 사유)를 보여 준다.

    log: get_audit_log_detail() 결과
    """
    st.subheader(f"기록 #{log['log_id']}")
    st.write(
        f"**{log['created_at']}** · {log.get('employee_no') or '(알 수 없음)'}"
        f" ({log.get('role') or '-'} / {log.get('company_code') or '-'})"
    )
    st.write(f"행위: `{log['action_type']}` · 대상: {log.get('target_type') or '-'} {log.get('target_id') or ''}")

    if log["blocked"]:
        st.error(f"차단됨 — {log.get('block_reason') or '사유 없음'}")
    else:
        st.success("정상 처리됨")

    if log.get("query"):
        st.write(f"검색어·질문: {log['query']}")
    if log.get("result_count") is not None:
        st.write(f"결과 건수: {log['result_count']}")

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
