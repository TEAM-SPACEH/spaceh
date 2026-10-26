"""M-01 로그인 세션 관리: is_authenticated(), get_current_user_id().

UI(Streamlit) 없이도 로그인을 실행·확인할 수 있게, 현재 로그인한 사용자 정보를
이 모듈의 메모리에 둔다. 화면을 붙일 때 st.session_state로 바꾸면 된다.
"""

# 현재 로그인한 사용자 정보. 로그인 전에는 None.
_current_user: dict | None = None


def set_current_user(user: dict) -> None:
    """M-01 로그인 성공 시 현재 사용자 정보를 세션에 저장한다 (auth_service가 부른다)."""
    global _current_user
    _current_user = user


def clear_current_user() -> None:
    """M-01 로그아웃 시 세션의 사용자 정보를 지운다 (auth_service가 부른다)."""
    global _current_user
    _current_user = None


def is_authenticated() -> bool:
    """M-01 현재 세션에 유효한 로그인 사용자가 있는지 판단한다."""
    return bool(_current_user and _current_user.get("employee_id"))


def get_current_user_id() -> str | None:
    """M-01 로그인한 사용자의 사원번호(사용자 ID)를 돌려준다. 로그인 전이면 None."""
    return _current_user.get("employee_id") if _current_user else None
