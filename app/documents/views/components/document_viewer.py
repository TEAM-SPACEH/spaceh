"""S-05 내부 문서 뷰어: 권한 재확인 후 PDF 해당 페이지 이미지와 근거 문단을 보여 준다."""

import logging

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import empty_state, highlight_html, no_permission_notice, show_text
from app.documents.services.document_service import (
    download_document,
    get_page_image,
    get_source_page,
    get_viewer_document,
)
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.permissions.services.permission_service import request_document_access

logger = logging.getLogger(__name__)

# 파일 형식 → 다운로드할 때 브라우저에 알려 줄 파일 종류
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# 열람 감사 로그를 이미 남긴 출처 (문서 ID, 위치). 화면이 다시 그려져도 같은 출처면 또 남기지 않아요.
AUDITED_SOURCE_KEY = "s05_audited_source"


def render_selected_source(user: dict | None = None) -> None:
    """S-05 출처 배지에서 고른 출처를 원문 뷰어로 연다. 고른 출처가 없으면 안내만 표시한다."""
    # 출처 배지와 원문 뷰어를 잇는 다리예요.
    # 배지의 [원문 보기]는 고른 출처를 세션(SELECTED_SOURCE_KEY)에 넣기만 하고,
    # 이 함수가 그 값을 꺼내 render_document_viewer()에 doc_id와 위치를 넘겨요.
    # 답변 화면(S-04)에서는 이렇게 두 줄만 쓰면 돼요.
    #   render_source_badge(result["sources"])
    #   render_selected_source()
    user = user or get_current_user()  # 검색 화면(S-01)처럼 넘겨받은 사용자가 없으면 로그인 사용자를 써요
    if not user:
        st.warning("로그인 후 원문을 볼 수 있습니다.")
        return

    source = st.session_state.get(SELECTED_SOURCE_KEY)
    if source is None:
        empty_state("출처의 [원문 보기]를 누르면 여기에 원문이 표시됩니다.")
        return

    render_document_viewer(source["doc_id"], source, user)

    # 닫기를 누르면 세션의 출처를 지우고 다시 그려서 뷰어를 닫아요.
    if st.button("원문 닫기", key="s05_close_viewer"):
        del st.session_state[SELECTED_SOURCE_KEY]
        # 기록 표시도 지워요. 닫았다가 다시 열면 새 열람이라 다시 1건 남아야 해서예요.
        st.session_state.pop(AUDITED_SOURCE_KEY, None)
        st.rerun()


def render_document_viewer(doc_id: str, location: dict, user: dict) -> None:
    """S-05 권한 재확인 후 PDF 해당 페이지 이미지와 근거 문단을 표시한다."""
    # location = 배지에서 고른 출처 그대로예요 (S-04 sources 한 개).
    #   {"text": 근거 문단, "company", "filename", "location": "p.3", "doc_id", ...}
    # 📌 명세서에는 location 모양이 없어서 이렇게 정했어요. 팀에 공유가 필요해요.

    # ① 권한 재확인 + 문서 정보 (판단은 services가 해요)
    # Streamlit은 버튼을 누를 때마다 이 함수를 다시 실행해요. 권한 확인은 매번 하되,
    # 열람 감사 로그는 "새로 연 출처"일 때만 남겨요. (같은 출처를 보는 동안에는 1건)
    opened = (doc_id, location.get("location"))                       # 지금 연 출처
    first_open = st.session_state.get(AUDITED_SOURCE_KEY) != opened    # 아직 기록 안 한 출처면 True
    document = get_viewer_document(doc_id, user, audit=first_open)
    st.session_state[AUDITED_SOURCE_KEY] = opened                      # 이 출처는 기록했다고 표시
    if document is None:
        st.error("문서를 찾을 수 없습니다. 삭제되었거나 다시 색인 중일 수 있습니다.")
        return

    # ② 권한이 없으면 제목만 보여 주고 본문·근거 문단은 보여 주지 않아요.
    if not document["can_view"]:
        # [열람 권한 요청] 버튼을 누르면 사유 입력 폼을 연다(M-03). 연 상태를 세션에 저장해
        # 사유를 적다가 화면이 재실행돼도 폼이 닫히지 않게 한다.
        open_key = f"s05_request_open_{doc_id}"
        if no_permission_notice(document["title"], location["company"], key=f"s05_{doc_id}"):
            st.session_state[open_key] = True
        if st.session_state.get(open_key):
            _render_access_request_form(doc_id, user)
        return

    # ③ 제목과 근거 문단. 데이터에서 온 글자라 공통 UI 함수로만 보여 줘요.
    show_text(document["title"], bold=True)
    show_text(location["location"], muted=True)
    st.html(highlight_html(location["text"]))  # 근거 문단을 옐로 하이라이트로 강조

    # ④ DART 공시는 우리 앱에 원본이 없어서 DART 뷰어로 보내요.
    if document["source_type"] == "dart":
        if document["dart_url"]:
            st.link_button("DART에서 원문 보기", document["dart_url"])
        else:
            st.warning("DART 접수번호가 없어 원문으로 연결할 수 없습니다.")
        return

    # ⑤ PDF는 해당 페이지를 이미지로 보여 줘요.
    if document["file_format"] == "pdf":
        image = get_page_image(doc_id, get_source_page(location), user)
        if image is None:
            st.warning("페이지 이미지를 불러올 수 없습니다. 근거 문단만 표시합니다.")
        else:
            st.image(image, width="stretch")
    else:
        # DOCX·PPTX 텍스트 뷰어는 다음 단계라, 지금은 근거 문단만 보여 줘요.
        st.info("이 형식은 페이지 이미지를 지원하지 않습니다. 근거 문단만 표시합니다.")

    _render_download(document, user)


def _render_access_request_form(doc_id: str, user: dict) -> None:
    """S-05 뷰어에서 권한 없는 문서의 열람 권한을 요청한다(M-03).

    사유(5~500자)를 받아 permission_service에 넘긴다. 판단·검증·저장은 모두 서비스가 하고,
    여기서는 입력을 받아 넘기고 결과만 안내한다(계층 규칙: views → services). 검색 화면의
    요청 폼과 같은 흐름이다.
    """
    reason = st.text_area("요청 사유 (5~500자)", key=f"s05_reason_{doc_id}")
    if not st.button("요청 보내기", key=f"s05_send_{doc_id}"):
        return

    try:
        registered = request_document_access(user["id"], doc_id, reason)
    except Exception:
        # 동시 요청 시 DB 데드락(1213) 등으로 예외가 올라올 수 있다. 앱을 멈추지 않고 안내한다.
        logger.exception("S-05 열람 권한 요청 등록 실패")
        st.error("요청 처리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if registered:
        st.success("열람 권한을 요청했습니다. 소유 회사 관리자의 승인 후 볼 수 있습니다.")
        # 이미 요청했으니 폼을 닫는다(같은 문서에 또 열지 않게).
        st.session_state.pop(f"s05_request_open_{doc_id}", None)
    else:
        st.error("요청을 등록하지 못했습니다. 사유(5~500자)를 확인하거나, 이미 요청한 문서인지 확인해 주세요.")


def _render_download(document: dict, user: dict) -> None:
    """원본 다운로드: 버튼을 누르는 순간 권한을 다시 확인하고 파일을 읽는다."""
    doc_id = document["doc_id"]

    def read_file_on_click() -> bytes:
        # data에 파일 내용 대신 "함수"를 넘기면, Streamlit은 화면을 그릴 때가 아니라
        # 사용자가 버튼을 누른 순간에 이 함수를 실행해요.
        # 그래서 화면을 띄운 뒤에 공유가 꺼지거나 승인이 취소돼도, 누르는 순간의 권한으로 다시 판단해요.
        # (예전에는 미리 읽은 파일을 세션에 넣어 둬서, 권한이 사라진 뒤에도 그 파일을 받을 수 있었어요.)
        file_bytes = download_document(doc_id, user)  # 여기서 권한 재확인 + 파일 읽기
        if file_bytes is None:
            # 오류를 내면 Streamlit이 다운로드를 멈추고 브라우저에 실패를 알려요.
            # 빈 파일을 돌려주지 않는 이유: 사용자가 "받아졌다"고 오해하지 않게 하려고요.
            # 이 함수 안에서는 st.* 화면 명령이 무시돼서 안내 문구 대신 오류를 내요.
            raise PermissionError(f"S-05 원본 다운로드 거부 doc_id={doc_id}")
        return file_bytes

    st.download_button(
        "원본 다운로드",
        data=read_file_on_click,  # 괄호 없이 함수 자체를 넘겨요. 괄호를 붙이면 지금 바로 실행돼 버려요.
        file_name=document["file_name"],
        mime=MIME_TYPES.get(document["file_format"], "application/octet-stream"),
        key=f"s05_download_{doc_id}",
    )
