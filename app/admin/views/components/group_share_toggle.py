"""A-03 그룹사 공유 토글 UI: render_group_share_toggle()."""

import logging
from collections.abc import Callable

import streamlit as st

from app.admin.services.access_service import set_group_share
from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL

logger = logging.getLogger(__name__)

_CONFIDENTIAL_NOTICE = "🔒 기밀 공유 불가"


def render_group_share_toggle(
    doc: dict,
    user: dict,
    on_toggle_callback: Callable[[str, bool], None] | None = None,
    *,
    key_prefix: str = "group-share",
) -> None:
    """A-03 문서 1건의 그룹사 공유 토글을 그린다.

    doc: get_manageable_documents() 결과의 문서 dict (doc_id·access_level·is_group_shared 필요)
    user: 로그인 사용자
    on_toggle_callback: 변경에 성공한 뒤 부르는 함수. (doc_id, 바뀐 공유 상태) 를 받는다
    key_prefix: 같은 문서의 토글을 화면의 여러 곳(표·패널)에 둘 때 위젯 이름이 겹치지 않게 붙이는 접두어
    confidential 은 꺼진 채 잠그고, internal 만 바꿀 수 있다.
    """
    state = bool(doc["is_group_shared"])
    level = doc["access_level"]
    # key: Streamlit 이 "이 토글은 이 문서의 것"이라고 구분하고 상태(켜짐/꺼짐)를 기억하는 이름표다.
    # 목록에는 토글이 여러 개라 문서마다 달라야 하고, 같은 문서를 표와 패널에 함께 그리면 접두어로도 달라야 한다.
    # 현재 공유 상태를 키에 넣는 이유: 한 곳에서 바꾸면 다른 곳의 토글은 옛 값을 기억하고 있어 어긋난다.
    # 상태가 바뀌면 키도 바뀌어 새 위젯으로 다시 그려지므로, 항상 DB 의 값을 따른다.
    key = f"{key_prefix}-{doc['doc_id']}-{int(state)}"

    # 화면은 "무엇을 보여줄지"만 정한다. 실제로 바꿔도 되는지는 서비스(set_group_share)가 다시 확인하므로
    # 여기서 잠그는 것은 사용자 안내용이다. 화면만 믿고 권한을 판단하지 않는다.
    if level == ACCESS_CONFIDENTIAL:
        st.toggle(
            "그룹사 공유", value=False, key=key, disabled=True, help=_CONFIDENTIAL_NOTICE, label_visibility="collapsed"
        )
        st.caption(_CONFIDENTIAL_NOTICE)
        return
    if level != ACCESS_INTERNAL:
        st.caption("공유 설정 대상이 아닙니다.")
        return

    # 값이 바뀌면 화면을 다시 그리기 전에 _on_change 가 먼저 실행된다. 그래서 같은 실행에서
    # 목록을 새로 읽는 화면(sharing.py)은 바뀐 값을 바로 보여 준다.
    st.toggle(
        "그룹사 공유",
        value=state,
        key=key,
        label_visibility="collapsed",
        on_change=_on_change,
        args=(doc, user, key, on_toggle_callback),
    )


def _on_change(doc: dict, user: dict, key: str, on_toggle_callback: Callable[[str, bool], None] | None) -> None:
    """토글이 바뀌면 서비스로 저장하고 결과를 토스트로 알린다. 실패하면 토글을 원래 값으로 되돌린다."""
    # Streamlit 은 위젯이 바뀌면 이 함수(on_change)를 먼저 실행한 뒤 화면 전체를 다시 그린다.
    # st.session_state[key] 에는 사용자가 방금 바꾼 토글 값이 들어 있다.
    desired = bool(st.session_state[key])
    # 실패했을 때 되돌릴 "원래 값"은 이 토글을 그릴 때 받은 doc 의 값이다.
    previous = bool(doc["is_group_shared"])
    try:
        result = set_group_share(doc["doc_id"], desired, user)
    except (PermissionError, ValueError, LookupError) as exc:
        # 서비스가 쉬운 말로 쓴 안내 문구라 그대로 보여 준다. 토글을 되돌리지 않으면 화면은 켜진 채인데
        # DB 는 꺼진 상태로 어긋난다.
        st.session_state[key] = previous
        st.toast(str(exc), icon="⚠️")
        return
    except Exception:
        # 그 밖의 오류(DB·Chroma 장애 등)는 내용이 사용자에게 보여 줄 말이 아니므로 로그에만 남기고 안내는 일반 문구로 한다.
        logger.exception("A-03 그룹사 공유 변경 실패: doc_id=%s", doc["doc_id"])
        st.session_state[key] = previous
        st.toast("공유 설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.", icon="⚠️")
        return

    st.toast(result["message"], icon="✅")
    if on_toggle_callback is not None:
        on_toggle_callback(result["doc_id"], result["is_group_shared"])
