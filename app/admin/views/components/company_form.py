"""A-07 계열사 추가 UI: render_company_form()."""

import logging

import streamlit as st

from app.admin.services.company_service import create_company
from app.common.ui import card, show_text

logger = logging.getLogger(__name__)

# session_state 키. 입력값과 직전 오류 문구를 화면을 다시 그려도 기억한다.
NAME_KEY = "company-form-name"
CODE_KEY = "company-form-code"
DART_KEY = "company-form-dart"
SHARE_KEY = "company-form-share"
ERROR_KEY = "company-form-error"


def render_company_form(user: dict) -> None:
    """A-07 계열사 더하기 폼(회사명·코드·DART 고유번호·기본 그룹사 공유)을 카드로 그린다.

    user: 로그인 사용자 (등록할 때 서비스가 최종 어드민인지 다시 확인한다)
    등록에 실패하면 입력값을 그대로 두고 오류 문구를 폼 아래에 보여 주며, 성공하면 입력칸을 비운다.
    """
    with card("company-form"):
        st.html('<div class="sh-card-title">계열사 더하기</div>')
        # st.form: 입력하는 동안에는 화면을 다시 그리지 않고, 버튼(또는 Enter)을 눌렀을 때 한 번에 제출한다.
        with st.form("company-form", border=False):
            st.text_input("회사명", key=NAME_KEY, placeholder="예: 현대투자파트너스")
            st.text_input("코드", key=CODE_KEY, placeholder="영문 대문자 2–5자, 예: HIP")
            show_text("사원번호 앞부분으로 쓰여 나중에 바꿀 수 없습니다.", muted=True)
            st.text_input("DART 고유번호 (선택)", key=DART_KEY, placeholder="상장사만, 8자리", max_chars=8)

            text_col, toggle_col = st.columns([4, 1], vertical_alignment="center")
            with text_col:
                show_text("기본 그룹사 공유", bold=True)
                show_text("새 사내 문서를 올릴 때 공유를 켠 상태로 시작", muted=True)
            with toggle_col:
                st.toggle("기본 그룹사 공유", key=SHARE_KEY, label_visibility="collapsed")

            st.form_submit_button(
                "계열사 더하기", type="primary", icon=":material/add:", width="stretch", on_click=_submit, args=(user,)
            )

        error = st.session_state.get(ERROR_KEY)
        if error:
            st.error(error)


def _submit(user: dict) -> None:
    """제출 버튼 콜백(화면을 다시 그리기 전에 실행). 서비스로 등록하고, 성공하면 입력칸을 비운다."""
    try:
        result = create_company(
            user,
            st.session_state[NAME_KEY],
            st.session_state[CODE_KEY],
            st.session_state[DART_KEY],
            bool(st.session_state[SHARE_KEY]),
        )
    except (ValueError, PermissionError) as exc:
        # 서비스가 쉬운 말로 쓴 안내 문구라 그대로 보여 준다. 입력값은 지우지 않아 고쳐서 다시 낼 수 있다.
        st.session_state[ERROR_KEY] = str(exc)
        return
    except Exception:
        logger.exception("A-07 계열사 등록 실패")
        st.session_state[ERROR_KEY] = "계열사를 추가하지 못했습니다. 잠시 후 다시 시도해 주세요."
        return

    st.session_state[ERROR_KEY] = ""
    for key, empty in ((NAME_KEY, ""), (CODE_KEY, ""), (DART_KEY, ""), (SHARE_KEY, False)):
        st.session_state[key] = empty
    st.toast(result["message"], icon="✅")
