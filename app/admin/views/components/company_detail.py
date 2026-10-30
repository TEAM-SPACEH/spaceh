"""A-07 계열사 DART 연결 UI: render_dart_connection()."""

import html
import logging

import streamlit as st

from app.admin.services.company_service import set_dart_code
from app.common.ui import card, company_tag_html

logger = logging.getLogger(__name__)


def render_dart_connection(companies: list[dict], user: dict) -> None:
    """A-07 계열사별 DART 고유번호 연결 상태를 카드로 보여 주고, 고유번호를 입력·수정하게 한다.

    companies: get_companies() 결과
    user: 로그인 사용자 (저장할 때 서비스가 최종 어드민인지 다시 확인한다)
    비상장사는 고유번호가 없으므로 "입력 전"으로 보인다 (companies 에 상장 여부 컬럼이 없어 구분하지 않는다).
    """
    with card("company-dart"):
        st.html('<div class="sh-card-title">DART 연결</div>')
        for company in companies:
            text_col, action_col = st.columns([4, 1], vertical_alignment="center")
            # 회사 코드와 고유번호도 입력된 값이라 html.escape 한 뒤 HTML 로 그린다.
            status = f"고유번호 {company['dart_code']}" if company["dart_code"] else "고유번호 입력 전"
            text_col.html(f'<div>{company_tag_html(company["company_id"])} {html.escape(status)}</div>')
            with action_col:
                _render_dart_input(company, user)


def _render_dart_input(company: dict, user: dict) -> None:
    """회사 한 곳의 고유번호 입력 칸을 팝오버로 그린다 ("입력" 또는 "수정")."""
    code = company["dart_code"] or ""
    # key 에 현재 저장된 값을 넣는 이유: 저장하면 값이 바뀌어 키도 바뀌고, 입력 칸이 새 값으로 다시 그려진다.
    # (같은 키를 쓰면 Streamlit 이 이전에 입력한 글자를 기억하고 있어 저장된 값과 어긋난다.)
    key = f"dart-input-{company['company_id']}-{code}"
    with st.popover("수정" if code else "입력"):
        st.text_input("DART 고유번호", value=code, key=key, placeholder="상장사만, 숫자 8자리", max_chars=8)
        st.button("저장", key=f"{key}-save", on_click=_save, args=(user, company["company_id"], key))


def _save(user: dict, company_id: str, key: str) -> None:
    """저장 버튼을 누르면 서비스로 저장하고 결과를 토스트로 알린다 (버튼 콜백은 화면을 다시 그리기 전에 실행된다)."""
    try:
        result = set_dart_code(user, company_id, st.session_state[key])
    except (ValueError, PermissionError, LookupError) as exc:
        # 서비스가 쉬운 말로 쓴 안내 문구라 그대로 보여 준다.
        st.toast(str(exc), icon="⚠️")
        return
    except Exception:
        logger.exception("A-07 DART 고유번호 저장 실패: company_id=%s", company_id)
        st.toast("저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", icon="⚠️")
        return
    st.toast(result["message"], icon="✅")
