"""M-01 로그인 세션 관리: is_authenticated(), get_current_user_id().

로그인한 사용자 정보는 Streamlit 세션(st.session_state)에 둔다. st.session_state는
브라우저(접속)마다 따로 보관되므로, 한 서버에 여러 사람이 붙어도 세션이 섞이지 않는다.
다른 패키지는 st.session_state를 직접 건드리지 말고 아래 함수로만 현재 사용자를 읽는다.
"""

import streamlit as st

# 세션에 사용자 정보를 담는 키. 바깥에서는 쓰지 말고 함수로만 접근한다.
_SESSION_USER_KEY = "auth_user"


def set_current_user(user: dict) -> None:
    """M-01 로그인 성공 시 현재 사용자(id·사원번호·이름·역할·소속)를 세션에 저장한다."""
    st.session_state[_SESSION_USER_KEY] = user


def clear_current_user() -> None:
    """M-01 로그아웃 시 세션의 사용자 정보를 지운다."""
    st.session_state.pop(_SESSION_USER_KEY, None)


def get_current_user() -> dict | None:
    """M-01 현재 로그인한 사용자 정보(dict)를 돌려준다. 로그인 전이면 None.

    S-03 권한 필터 등 다른 패키지가 역할(role)·소속(company_id)을 읽는 입구다.
    """
    return st.session_state.get(_SESSION_USER_KEY)


def is_authenticated() -> bool:
    """M-01 현재 세션에 유효한 로그인 사용자가 있는지 판단한다."""
    user = get_current_user()
    return bool(user and user.get("id"))


def get_current_user_id() -> int | None:
    """M-01 로그인한 사용자의 DB id(users.id)를 돌려준다. 로그인 전이면 None."""
    user = get_current_user()
    return user.get("id") if user else None
