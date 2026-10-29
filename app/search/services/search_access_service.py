
"""검색 결과 및 AI 답변 표시 전 최신 접근 권한을 확인하는 서비스."""

from app.auth.repositories.user_repository import find_user_by_employee_no
from app.documents.repositories.document_repository import find_by_id
from app.permissions.repositories.permission_repository import get_approved_doc_ids
from app.permissions.services.permission_service import check_search_permission


def get_fresh_search_user(user: dict) -> dict:
    """DB의 최신 사용자 정보로 검색 권한을 확인한다."""

    if not isinstance(user, dict):
        raise PermissionError("로그인이 필요합니다.")

    employee_no = user.get("employee_no")
    user_id = user.get("id")

    if not employee_no or user_id is None:
        raise PermissionError("사용자 정보를 확인할 수 없습니다.")

    current = find_user_by_employee_no(employee_no)

    if (
        not current
        or not current.get("is_active")
        or str(current["id"]) != str(user_id)
    ):
        raise PermissionError("사용자 계정이 유효하지 않습니다.")

    # password_hash 등 불필요한 개인정보는 전달하지 않는다.
    return {
        "id": current["id"],
        "employee_no": current["employee_no"],
        "name": current["name"],
        "role": current["role"],
        "company_id": current["company_id"],
        "company_name": current["company_name"],
    }


def inspect_search_access(
    user: dict,
    chunks: list[dict],
) -> tuple[list[dict], tuple]:
    """검색 청크를 최신 DB 권한으로 검증하고 권한 상태를 반환한다."""

    if not isinstance(user, dict) or user.get("id") is None:
        raise PermissionError("사용자 정보를 확인할 수 없습니다.")

    # 승인 문서 변경도 감지하기 위해 스냅샷에 포함한다.
    approved_ids = tuple(
        sorted(str(doc_id) for doc_id in get_approved_doc_ids(user["id"]))
    )

    documents = {}
    document_snapshots = {}
    authorized_chunks = []

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}

        chunk_doc_id = chunk.get("doc_id")
        metadata_doc_id = metadata.get("doc_id")

        # 청크와 메타데이터의 문서 ID가 다르면 사용하지 않는다.
        if (
            chunk_doc_id
            and metadata_doc_id
            and str(chunk_doc_id) != str(metadata_doc_id)
        ):
            continue

        doc_id = chunk_doc_id or metadata_doc_id

        if not doc_id:
            continue

        doc_id = str(doc_id)

        # 동일 문서는 DB에서 한 번만 조회한다.
        if doc_id not in documents:
            documents[doc_id] = find_by_id(doc_id)

        document = documents[doc_id]

        # 삭제되었거나 현재 접근할 수 없는 문서는 제외한다.
        if not document or not check_search_permission(user, document):
            continue

        # Chroma 메타데이터와 실제 DB 권한 정보 비교
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

        # 인덱스의 권한 정보가 오래되었으면 해당 청크 제외
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
        user.get("role"),
        str(user.get("company_id")),
        approved_ids,
        tuple(sorted(document_snapshots.items())),
    )

    return authorized_chunks, snapshot
