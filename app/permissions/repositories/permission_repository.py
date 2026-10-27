"""S-03 승인 내역 조회."""


def get_approved_doc_ids(user_id: int) -> list[str]:
    """S-03 사용자가 열람 승인(A-05)을 받은 문서의 doc_id 목록을 반환한다."""
    # document_permissions 테이블이 아직 ERD·schema.sql에 없어 승인 문서는 없는 것으로 본다.
    # 테이블이 추가되면 %s 바인딩 SELECT로 바꾼다.
    return []
