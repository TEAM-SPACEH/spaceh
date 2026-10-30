"""A-06 다운로드 허용·차단·워터마크 판정: decide_report_download().

보고서를 파일(Markdown·DOCX)로 내려받게 하기 전에 "이 사용자가 이 보고서를 받아도 되는가"를 정한다.
보고서는 여러 문서를 근거로 쓰므로, 근거 문서를 하나라도 볼 수 없는 사용자에게는 파일을 주지 않는다.
(파일은 화면과 달리 밖으로 나가 버리기 때문이다.)

규칙 (docs/architecture/overview.md §2.3-4)
- 보고서를 만든 뒤 권한이 바뀌었을 수 있으므로, 근거 문서마다 접근 권한을 DB 기준으로 다시 확인한다.
- 하나라도 못 보는 문서가 있으면 보고서 전체를 차단한다. 일부만 빼고 내보내면 본문의 각주 번호가 어긋난다.
- 차단된 시도는 감사 로그(A-04)에 남긴다. 허용된 다운로드의 기록은 파일을 실제로 만드는 쪽(R-05)이 남긴다.

이 파일은 판정만 한다. 파일 만들기(R-05)와 다운로드 버튼(화면)은 여기서 하지 않는다.
"""

import logging
from datetime import datetime

from app.admin.services.audit_service import KST, record_audit_log
from app.permissions.services.permission_service import check_document_access
from core.constants import ACCESS_CONFIDENTIAL

logger = logging.getLogger(__name__)

# 내려받을 수 있는 파일 형식 (R-05 내보내기 형식과 같다).
DOWNLOAD_FORMATS = ("md", "docx")

# 워터마크 문구 (R-05와 합의한 형식). 예: 워터마크: 박사원(MVX-0001) · 2026-10-30 13:40 다운로드 · 외부 유출 금지
WATERMARK_TEMPLATE = "워터마크: {name}({employee_no}) · {downloaded_at} 다운로드 · 외부 유출 금지"


def decide_report_download(
    user: dict | None,
    doc_ids: list[str],
    file_format: str,
    report_id: str | None = None,
    *,
    max_access_level: str | None = None,
) -> dict:
    """A-06 사용자가 이 보고서를 파일로 받아도 되는지 판정한다.

    user: 로그인 사용자. {"id": 3, "role": "employee", "company_id": "MVX"} 모양
    doc_ids: 보고서 근거(각주)에 쓰인 문서 ID 목록. 중복이 있어도 된다.
    file_format: "md" 또는 "docx". 그 밖의 값은 부르는 쪽 실수이므로 ValueError
    report_id: 감사 로그에 남길 보고서 ID. 아직 저장 전이면 None
    max_access_level: 보고서 근거 중 가장 높은 보안 등급(Report.max_access_level).
        "confidential"이면 열람 권한과 관계없이 차단한다 (docs/decisions.md 10/30)
    반환: {
        "allowed": True/False,
        "reason": 차단 사유 (허용이면 None),
        "watermark": 파일에 넣을 문구 (차단이면 None),
        "blocked_doc_ids": 사용자가 볼 수 없는 문서 ID 목록,
    }
    """
    if file_format not in DOWNLOAD_FORMATS:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {file_format}")

    user_id = user.get("id") if user else None
    # 중복을 없애되 순서는 지킨다 (감사 로그·차단 목록이 보고서 각주 순서와 맞도록).
    unique_ids = list(dict.fromkeys(doc_ids or []))

    if user_id is None:
        return _block(user, report_id, unique_ids, "로그인한 사용자만 내려받을 수 있습니다.", [])

    # 근거 문서가 없으면 어떤 문서로 만든 보고서인지 알 수 없어 권한을 확인할 수 없다.
    if not unique_ids:
        return _block(user, report_id, unique_ids, "근거 문서 정보가 없어 권한을 확인할 수 없습니다.", [])

    # 기밀 문서가 근거에 있으면 볼 권한이 있어도 파일로는 내보내지 않는다. 기밀은 그룹사 공유도 못 하는 등급이다.
    if max_access_level == ACCESS_CONFIDENTIAL:
        return _block(user, report_id, unique_ids, "기밀 문서가 포함된 보고서는 내려받을 수 없습니다.", [])

    blocked_ids = [doc_id for doc_id in unique_ids if not check_document_access(user_id, doc_id)]
    if blocked_ids:
        reason = f"열람 권한이 없는 근거 문서가 {len(blocked_ids)}건 포함되어 있습니다."
        return _block(user, report_id, unique_ids, reason, blocked_ids)

    return {
        "allowed": True,
        "reason": None,
        "watermark": _make_watermark(user),
        "blocked_doc_ids": [],
    }


def _make_watermark(user: dict) -> str:
    """파일에 넣을 워터마크 문구. 유출됐을 때 누가 받은 파일인지 알 수 있게 사용자와 시각을 넣는다."""
    return WATERMARK_TEMPLATE.format(
        name=user.get("name") or "이름 없음",
        employee_no=user.get("employee_no") or f"사용자 {user['id']}",
        downloaded_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    )


def _block(user: dict | None, report_id: str | None, doc_ids: list[str], reason: str, blocked_ids: list[str]) -> dict:
    """차단 결과를 만들고 감사 로그를 남긴다. 기록 실패가 판정을 막으면 안 되므로 로그만 남기고 넘어간다."""
    try:
        record_audit_log(
            user.get("id") if user else None,
            "download",
            report_id,
            None,
            True,
            reason,
            target_type="report",
            doc_ids=doc_ids,
        )
    except Exception:
        logger.exception("보고서 다운로드 차단 감사 로그 기록 실패")
    return {"allowed": False, "reason": reason, "watermark": None, "blocked_doc_ids": blocked_ids}
