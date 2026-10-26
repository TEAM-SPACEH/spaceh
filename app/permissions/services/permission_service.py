"""S-03 권한 기반 사전 필터링: apply_rbac_filter(), check_search_permission().

이 파일은 "누가 어떤 문서를 볼 수 있는가"를 정하는 유일한 곳이다.
검색(S-01)·질의응답(S-04)·보고서 수집(R-01)·원문 보기(S-05)는 모두 여기 함수를 거친다.
규칙 원본은 docs/architecture/overview.md §2.1 열람 매트릭스다.

용어
- RBAC(역할 기반 접근 제어): 사용자의 역할(일반 사원·계열사 관리자·최종 어드민)에 따라
  볼 수 있는 범위를 정하는 방식.
- 사전 필터: 검색을 먼저 하고 결과를 거르는 것이 아니라, 검색 조건(Chroma where)에 권한을
  넣어서 볼 수 없는 문서가 아예 검색 후보에 들어오지 않게 하는 것. 이렇게 해야 권한 없는
  문서 내용이 LLM에 들어갈 길이 처음부터 막힌다.
"""

from app.permissions.repositories.permission_repository import get_approved_doc_ids

ROLES = ("employee", "company_admin", "super_admin")


def apply_rbac_filter(user: dict, filters: dict | None) -> dict:
    """S-03 벡터 유사도 연산 전에 미인가 문서를 제외하는 Chroma where 조건을 만든다.

    user: 로그인 사용자. {"id": 3, "role": "employee", "company_id": "MVX"} 모양
    filters: S-02 화면 필터(회사·문서 유형·기간)로 만든 Chroma where 식. 없으면 None 또는 {}
    반환: Chroma where 식. 예) 현대무벡스 일반 사원
        {"$or": [
            {"access_level": "public"},                                        # 전사 공개
            {"$and": [{"company_id": "MVX"}, {"access_level": "internal"}]},   # 자사 내부
            {"$and": [{"access_level": "internal"}, {"is_group_shared": True}]},  # 공유 ON
        ]}
    """
    conditions = _allowed_conditions(user)

    # 최종 어드민은 권한 제한이 없어 S-02 필터만 남는다.
    # 필터도 없으면 빈 dict를 돌려주는데, Chroma는 빈 where를 오류로 처리하므로
    # 부르는 쪽은 collection.query(..., where=결과 or None)처럼 넘긴다.
    if conditions is None:
        return filters or {}

    # 허용 조건 중 "하나라도" 맞으면 볼 수 있으므로 $or로 묶는다.
    rbac_where = {"$or": [_to_where(condition) for condition in conditions]}
    if not filters:
        return rbac_where

    # 권한 조건과 화면 필터를 "둘 다" 만족해야 하므로 $and로 묶는다.
    return {"$and": [rbac_where, filters]}


def check_search_permission(user: dict, document: dict) -> bool:
    """S-03 사용자 역할·소속 기업·문서 보안 등급·공유 여부·승인 내역으로 문서 접근 가능 여부를 확인한다.

    원문 보기·다운로드·보고서 다시 열기 직전에 문서 1건을 다시 확인할 때 쓴다.
    검색할 때는 볼 수 있었어도 그 사이 공유가 꺼지거나 승인이 취소됐을 수 있기 때문이다.

    document: Chroma 메타데이터 또는 MySQL documents 행(dict).
              doc_id·company_id·access_level·is_group_shared 값을 읽는다.
    """
    if not document:
        return False

    # 잘못된 사용자 정보는 예외를 내는 대신 "볼 수 없음"으로 답한다.
    # 이 함수는 화면에서 바로 열람 여부를 판단하는 데 쓰이기 때문이다.
    try:
        conditions = _allowed_conditions(user)
    except PermissionError:
        return False

    if conditions is None:  # 최종 어드민
        return True
    return any(_matches(condition, document) for condition in conditions)


def _allowed_conditions(user: dict) -> list[dict] | None:
    """열람 매트릭스(overview §2.1)를 "허용 조건 목록"으로 만든다. None이면 제한 없음(super_admin).

    목록의 조건 하나는 "이 필드들이 모두 이 값이면 볼 수 있다"는 뜻이다.
    예) {"company_id": "MVX", "access_level": "internal"} → 현대무벡스의 내부 문서는 볼 수 있다.

    검색 필터(apply_rbac_filter)와 문서 1건 확인(check_search_permission)이 모두 이 목록 하나만
    보게 해서, 두 곳의 판정이 서로 어긋나는 일이 없게 한다. 규칙을 바꿀 때는 여기만 고친다.
    """
    # 로그인 정보가 없거나 모르는 역할이면 아무것도 보여 주지 않는다 (안전한 쪽으로 실패).
    if not user or user.get("role") not in ROLES:
        raise PermissionError("알 수 없는 사용자입니다.")
    if user["role"] == "super_admin":
        return None

    # super_admin이 아닌데 소속 회사가 없으면 "자사" 기준을 정할 수 없으므로 막는다.
    company_id = user.get("company_id")
    if not company_id:
        raise PermissionError("소속 회사가 없는 사용자입니다.")

    conditions = [
        # 1) 전사 공개 문서는 누구나 본다.
        {"access_level": "public"},
        # 2) 우리 회사 내부 문서는 본다.
        {"company_id": company_id, "access_level": "internal"},
        # 3) 다른 회사 문서라도 그룹사 공유가 켜진 내부 문서는 본다.
        #    confidential(계약 단가 등)은 공유 대상이 아니므로 internal로 한정한다.
        #    공유 플래그가 잘못 켜진 confidential 문서가 있어도 여기서 새지 않는다.
        {"access_level": "internal", "is_group_shared": True},
    ]

    # 4) 계열사 관리자는 우리 회사 기밀 문서도 본다. 일반 사원은 승인을 받아야 한다.
    if user["role"] == "company_admin":
        conditions.append({"company_id": company_id, "access_level": "confidential"})

    # 5) 열람 권한 요청(M-03)이 승인(A-05)된 문서는 등급·회사와 관계없이 본다.
    approved_doc_ids = get_approved_doc_ids(user["id"])
    # Chroma는 빈 목록으로 $in 검색을 하면 오류가 나서, 승인 문서가 있을 때만 조건을 넣는다.
    if approved_doc_ids:
        conditions.append({"doc_id": {"$in": approved_doc_ids}})
    return conditions


def _to_where(condition: dict) -> dict:
    """허용 조건 하나를 Chroma where 식으로 바꾼다."""
    # Chroma where 식은 dict 하나에 키를 하나만 둘 수 있다.
    # 그래서 {"company_id": "MVX", "access_level": "internal"}처럼 필드가 여럿이면
    # {"$and": [{"company_id": "MVX"}, {"access_level": "internal"}]}로 풀어 쓴다.
    if len(condition) == 1:
        return condition
    return {"$and": [{field: value} for field, value in condition.items()]}


def _matches(condition: dict, document: dict) -> bool:
    """문서 1건이 허용 조건 하나를 만족하는지 확인한다 (Chroma where를 파이썬으로 흉내 낸 것)."""
    for field, expected in condition.items():
        actual = document.get(field)
        if isinstance(expected, dict):
            # {"$in": [...]} 형태: 문서 값이 목록 안에 있어야 한다 (승인 문서 목록).
            if actual not in expected["$in"]:
                return False
        # MySQL은 is_group_shared를 1/0으로 주지만, 파이썬에서 1 == True라서 그대로 비교된다.
        elif actual != expected:
            return False
    return True
