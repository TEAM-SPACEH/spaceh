"""S-05 내부 문서 뷰어: 권한 재확인 후 PDF 해당 페이지 이미지와 근거 문단을 보여 준다."""

import streamlit as st

from app.common.ui import highlight_html, no_permission_notice, show_text
from app.documents.services.document_service import (
    download_document,
    get_page_image,
    get_source_page,
    get_viewer_document,
)

# 파일 형식 → 다운로드할 때 브라우저에 알려 줄 파일 종류
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def render_document_viewer(doc_id: str, location: dict, user: dict) -> None:
    """S-05 권한 재확인 후 PDF 해당 페이지 이미지와 근거 문단을 표시한다."""
    # location = 배지에서 고른 출처 그대로예요 (S-04 sources 한 개).
    #   {"text": 근거 문단, "company", "filename", "location": "p.3", "doc_id", ...}
    # 📌 명세서에는 location 모양이 없어서 이렇게 정했어요. 팀에 공유가 필요해요.

    # ① 권한 재확인 + 문서 정보 (판단은 services가 해요)
    document = get_viewer_document(doc_id, user)
    if document is None:
        st.error("문서를 찾을 수 없습니다. 삭제되었거나 다시 색인 중일 수 있습니다.")
        return

    # ② 권한이 없으면 제목만 보여 주고 본문·근거 문단은 보여 주지 않아요.
    if not document["can_view"]:
        if no_permission_notice(document["title"], location["company"], key=f"s05_{doc_id}"):
            # 📌 열람 권한 요청(M-03)은 이상훈님 담당이라, 완성되면 여기서 연결해요.
            st.info("열람 권한 요청 기능은 준비 중입니다.")
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


def _render_download(document: dict, user: dict) -> None:
    """원본 다운로드: [원본 파일 준비]를 눌렀을 때만 파일을 읽는다."""
    # 다운로드 버튼에 파일을 바로 넣으면 화면이 다시 그려질 때마다 파일을 읽고,
    # 감사 로그가 생기면 "다운로드"가 실제로 누르지 않아도 계속 쌓여요. 그래서 두 단계로 나눴어요.
    prepared_key = f"s05_file_{document['doc_id']}"

    if prepared_key not in st.session_state:
        if st.button("원본 파일 준비", key=f"s05_prepare_{document['doc_id']}"):
            file_bytes = download_document(document["doc_id"], user)  # 여기서 권한을 한 번 더 확인해요
            if file_bytes is None:
                st.error("원본 파일을 내려받을 수 없습니다.")
                return
            st.session_state[prepared_key] = file_bytes
            st.rerun()  # 바로 다시 그려서 다운로드 버튼을 보여 줘요
        return

    st.download_button(
        "원본 다운로드",
        data=st.session_state[prepared_key],
        file_name=document["file_name"],
        mime=MIME_TYPES.get(document["file_format"], "application/octet-stream"),
        key=f"s05_download_{document['doc_id']}",
    )
