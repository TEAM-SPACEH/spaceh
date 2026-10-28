
"""저장된 검색 결과의 최신 열람 권한 검증."""

from app.auth.repositories.user_repository import find_user_by_employee_no
from app.documents.repositories.document_repository import find_by_id
from app.permissions.repositories.permission_repository import get_approved_doc_ids
from app.permissions.services.permission_service import check_search_permission


def get_fresh_search_user(user: dict) -> dict:
    """DB에서 최신 사용자 권한을 조회한다."""

    employee_no = user.get("employee_no") if user else None

    if not employee_no or user.get("id") is None:
        raise PermissionError("사용자 정보를 확인할 수 없습니다.")

    current = find_user_by_employee_no(employee_no)

    if (
        not current
        or not current.get("is_active")
        or str(current["id"]) != str(user["id"])
    ):
        raise PermissionError("현재 계정을 사용할 수 없습니다.")

    # 비밀번호 해시는 검색 서비스에 전달하지 않는다.
    return {
        "id": current["id"],
        "employee_no": current["employee_no"],
        "name": current["name"],
        "role": current["role"],
        "company_id": current["company_id"],
        "company_name": current.get("company_name"),
    }


def inspect_search_access(user: dict, chunks: list[dict]) -> tuple[list[dict], tuple]:
    """현재 열람 가능한 청크와 권한 상태 스냅샷을 반환한다."""

    approved_ids = tuple(
        sorted(str(doc_id) for doc_id in get_approved_doc_ids(user["id"]))
    )

    documents = {}
    authorized_chunks = []
    document_snapshots = {}

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        doc_id = chunk.get("doc_id") or metadata.get("doc_id")

        # 문서를 식별할 수 없으면 안전하게 제외
        if not doc_id:
            continue

        doc_id = str(doc_id)

        if doc_id not in documents:
            documents[doc_id] = find_by_id(doc_id)

        document = documents[doc_id]

        if not document:
            continue

        if not check_search_permission(user, document):
            continue

        # Chroma의 권한 메타데이터와 현재 DB 값이 다르면 제외한다.
        # 공유 설정 변경 후 색인이 갱신되지 않은 상황도 방어한다.
        stale = False

        for field in ("company_id", "access_level", "is_group_shared"):
            if field not in metadata:
                continue

            old_value = metadata[field]
            new_value = document.get(field)

            if field == "is_group_shared":
                if bool(old_value) != bool(new_value):
                    stale = True
                    break
            elif str(old_value) != str(new_value):
                stale = True
                break

        if stale:
            continue

        authorized_chunks.append(chunk)

        document_snapshots[doc_id] = (
            str(document.get("company_id")),
            str(document.get("access_level")),
            bool(document.get("is_group_shared")),
        )

    snapshot = (
        str(user["id"]),
        user["role"],
        user.get("company_id"),
        approved_ids,
        tuple(sorted(document_snapshots.items())),
    )

    return authorized_chunks, snapshot
