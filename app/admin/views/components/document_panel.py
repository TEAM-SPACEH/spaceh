"""A-02·A-03 표에서 고른 문서의 상세 패널: 보안 등급, 그룹사 공유 설정, 볼 수 있는 사람, 삭제·재색인."""

import html
import logging

import streamlit as st

from app.admin.services.access_service import set_group_share
from app.admin.services.document_service import get_document_detail
from app.admin.views.components.document_labels import access_tag_html, format_tile_html
from app.admin.views.components.document_list import confirm_delete, run_reindex
from app.common.ui import ACCESS_LABELS, card, company_tag_html, empty_state
from core.constants import ACCESS_INTERNAL

logger = logging.getLogger(__name__)

_NOT_SHAREABLE_NOTICE = "기밀 문서는 공유할 수 없습니다. 사내 문서만 켤 수 있어요."
_NOT_INDEXED_NOTICE = "색인이 끝난 뒤 바꿀 수 있습니다."


def _share_note(document: dict) -> str:
    """그룹사 공유 줄 아래 안내. 공유할 수 없는 이유, 아니면 지금 상태를 알려 준다."""
    if document["access_level"] != ACCESS_INTERNAL:
        return _NOT_SHAREABLE_NOTICE
    if document["index_status"] != "done":
        return _NOT_INDEXED_NOTICE
    return "켜면 다른 계열사 사용자도 볼 수 있습니다." if not document["is_group_shared"] else "켜져 있어 다른 계열사 사용자도 볼 수 있습니다."


def _viewers_html(viewers: list[dict]) -> str:
    """"볼 수 있는 사람" 줄들. 이름은 DB 값이라 escape하고, 회사 태그는 공통 함수를 쓴다."""
    rows = []
    for viewer in viewers:
        tag = company_tag_html(viewer["company_id"]) if viewer.get("company_id") else ""
        rows.append(
            f'<div class="sh-ad-viewer"><span>{html.escape(viewer["label"])}{tag}</span>'
            f'<em>{html.escape(viewer["note"])}</em></div>'
        )
    return "".join(rows)


def _save_share(document: dict, desired: bool, user: dict) -> None:
    """[변경 저장]: 그룹사 공유를 서비스로 저장하고 결과를 안내한다. 권한·등급은 서비스가 다시 확인한다."""
    try:
        result = set_group_share(document["doc_id"], desired, user)
    except (PermissionError, ValueError, LookupError) as exc:
        # 서비스가 쉬운 말로 쓴 안내 문구라 그대로 보여 준다.
        st.toast(str(exc), icon="⚠️")
        return
    except Exception:
        # 그 밖의 오류(DB·Chroma 장애 등)는 보여 줄 말이 아니므로 로그에만 남기고 일반 문구로 안내한다.
        logger.exception("A-03 그룹사 공유 변경 실패: doc_id=%s", document["doc_id"])
        st.toast("공유 설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.", icon="⚠️")
        return
    st.toast(result["message"], icon="✅")
    st.rerun()


def render_document_panel(user: dict, document: dict | None) -> None:
    """표에서 고른 문서의 상세를 오른쪽 패널로 보여 주고 공유 변경·삭제·재색인을 받는다.

    user: 로그인 사용자
    document: render_document_list()가 돌려준 문서. 없으면 안내만 보여 준다
    """
    with card("ad_panel"):
        if document is None:
            empty_state("표에서 문서를 고르면 자세한 정보가 여기에 보입니다.")
            return
        doc_id = document["doc_id"]
        try:
            detail = get_document_detail(doc_id, user)
        except (PermissionError, LookupError) as exc:
            st.warning(str(exc))
            return
        except Exception:
            logger.exception("A-03 문서 상세 조회 실패: doc_id=%s", doc_id)
            detail = None

        uploader = (detail or {}).get("uploader_name") or "알 수 없음"
        st.html(
            f'<div class="sh-ad-panel-head">{format_tile_html(document["file_format"], large=True)}'
            f'{access_tag_html(document["access_level"])}</div>'
            f'<div class="sh-ad-panel-title">{html.escape(document["title"])}</div>'
            f'<div class="sh-ad-panel-sub">올린 사람 {html.escape(uploader)}, {document["created_at"]:%m.%d}</div>'
        )

        # 보안 등급 변경은 명세에 없고 Chroma 메타데이터 동기화가 필요해 지원하지 않는다. 현재 값을 읽기 전용으로 보여 준다.
        level_label = ACCESS_LABELS.get(document["access_level"], document["access_level"])
        st.selectbox("보안 등급", [level_label], key=f"ad-panel-level-{doc_id}", disabled=True)

        can_share = document["access_level"] == ACCESS_INTERNAL and document["index_status"] == "done"
        current = bool(document["is_group_shared"])
        text_col, toggle_col = st.columns([220, 34], vertical_alignment="center")
        text_col.html(
            '<div class="sh-ad-share-title">그룹사 공유</div>'
            f'<div class="sh-ad-share-note">{html.escape(_share_note(document))}</div>'
        )
        # 현재 공유 상태를 key에 넣어, 표의 토글로 바꾼 값이 DB 기준으로 다시 맞춰지게 한다 (옛 값을 기억하지 않는다).
        with toggle_col:
            desired = st.toggle("그룹사 공유", value=current, key=f"ad-panel-share-{doc_id}-{int(current)}",
                                disabled=not can_share, label_visibility="collapsed")

        st.html('<div class="sh-ad-divider"></div>')
        if detail is not None:
            st.html('<div class="sh-ad-viewers-title">볼 수 있는 사람</div>' + _viewers_html(detail["viewers"]))
        else:
            st.html('<div class="sh-ad-viewers-title">볼 수 있는 사람</div>'
                    '<div class="sh-ad-share-note">목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>')

        with st.container(key="ad_panel_actions", horizontal=True):
            # 버튼을 끄는 것(disabled)은 안내용이다. 눌렀을 때 서비스가 권한·상태를 다시 확인한다.
            if st.button("삭제", key=f"admin-docs-delete-{doc_id}", disabled=not document["can_delete"],
                         help=None if document["can_delete"] else "색인 중인 문서는 삭제할 수 없습니다."):
                confirm_delete(document, user)
            if st.button("재색인", key=f"admin-docs-reindex-{doc_id}", disabled=not document["can_reindex"],
                         help=None if document["can_reindex"] else "원본이 없거나 처리 중인 문서는 다시 색인할 수 없습니다."):
                run_reindex(document, user)
            if st.button("변경 저장", key=f"ad-panel-save-{doc_id}", type="primary"):
                if desired == current:
                    st.toast("바꾼 내용이 없습니다.", icon="ℹ️")
                else:
                    _save_share(document, desired, user)
