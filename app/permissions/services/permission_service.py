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

import logging

from app.admin.services.audit_service import record_audit_log
from app.permissions.repositories.permission_repository import (
    find_document,
    find_user,
    get_approved_doc_ids,
    get_pending_doc_ids,
    has_pending_request,
    insert_access_request,
    list_access_requests_by_user,
)
from app.permissions.validators import validate_request_reason
from core.constants import (
    ACCESS_CONFIDENTIAL,
    ACCESS_INTERNAL,
    ACCESS_PUBLIC,
    ROLE_COMPANY_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLES,
)

logger = logging.getLogger(__name__)


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


def _allowed_conditions(user: dict, approved_doc_ids: list | None = None) -> list[dict] | None:
    """열람 매트릭스(overview §2.1)를 "허용 조건 목록"으로 만든다. None이면 제한 없음(super_admin).

    approved_doc_ids를 넘기면 승인 문서 조회(get_approved_doc_ids)를 생략한다. 여러 문서를
    한꺼번에 판정하는 배치 호출에서 같은 조회를 반복하지 않으려고 쓴다(안 넘기면 여기서 한 번 조회).

    목록의 조건 하나는 "이 필드들이 모두 이 값이면 볼 수 있다"는 뜻이다.
    예) {"company_id": "MVX", "access_level": "internal"} → 현대무벡스의 내부 문서는 볼 수 있다.

    검색 필터(apply_rbac_filter)와 문서 1건 확인(check_search_permission)이 모두 이 목록 하나만
    보게 해서, 두 곳의 판정이 서로 어긋나는 일이 없게 한다. 규칙을 바꿀 때는 여기만 고친다.
    """
    # 로그인 정보가 없거나 모르는 역할이면 아무것도 보여 주지 않는다 (안전한 쪽으로 실패).
    if not user or user.get("role") not in ROLES:
        raise PermissionError("알 수 없는 사용자입니다.")
    if user["role"] == ROLE_SUPER_ADMIN:
        return None

    # super_admin이 아닌데 소속 회사가 없으면 "자사" 기준을 정할 수 없으므로 막는다.
    company_id = user.get("company_id")
    if not company_id:
        raise PermissionError("소속 회사가 없는 사용자입니다.")

    conditions = [
        # 1) 전사 공개 문서는 누구나 본다.
        {"access_level": ACCESS_PUBLIC},
        # 2) 우리 회사 내부 문서는 본다.
        {"company_id": company_id, "access_level": ACCESS_INTERNAL},
        # 3) 다른 회사 문서라도 그룹사 공유가 켜진 내부 문서는 본다.
        #    confidential(계약 단가 등)은 공유 대상이 아니므로 internal로 한정한다.
        #    공유 플래그가 잘못 켜진 confidential 문서가 있어도 여기서 새지 않는다.
        {"access_level": ACCESS_INTERNAL, "is_group_shared": True},
    ]

    # 4) 계열사 관리자는 우리 회사 기밀 문서도 본다. 일반 사원은 승인을 받아야 한다.
    if user["role"] == ROLE_COMPANY_ADMIN:
        conditions.append({"company_id": company_id, "access_level": ACCESS_CONFIDENTIAL})

    # 5) 열람 권한 요청(M-03)이 승인(A-05)된 문서는 등급·회사와 관계없이 본다.
    #    배치 호출이 미리 넘겨 준 승인 목록이 있으면 그걸 쓰고, 없으면 여기서 한 번 조회한다.
    if approved_doc_ids is None:
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


# ─── M-03: "이 문서 봐도 돼요?" 확인과 "보게 해 주세요" 요청 ───
#
# 쉽게 말하면:
#  - 문서마다 '이름표'(doc_id)가 붙어 있다. 그 이름표로 문서를 찾는다.
#  - 볼 수 있는지 없는지는 아래 함수들이 정한다. "봐도 되면 True, 안 되면 False".
#  - 못 보는 문서는 "저 이거 보게 해 주세요"라고 요청을 남길 수 있다(관리자가 나중에 허락).
#
# 참고: doc_id는 숫자가 아니라 글자(문자열)다. 문서 이름표가 'ELV-spec-1' 같은 글자라서다.
# 요청 사유 검증(validate_request_reason)은 형식 검증 계층인 app/permissions/validators.py에 있다.


def check_document_access(user_id: int, doc_id: str) -> bool:
    """M-03 이 사람(user_id)이 이 문서(doc_id)를 볼 수 있는지 True/False로 알려준다.

    누가 무엇을 볼 수 있는지는 역할(사원/관리자), 소속 회사, 문서의 보안 등급,
    그룹사 공유 여부, 그리고 '봐도 된다'고 허락(승인)받았는지로 정해진다.
    그 판단은 이미 있는 check_search_permission 한 곳에 맡겨, 검색 화면과 규칙이 똑같게 한다
    (권한 규칙을 여기서 새로 만들지 않는다).
    """
    # 1) 사원 번호로 사람 정보를, 이름표로 문서 정보를 데이터베이스에서 찾아온다.
    user = find_user(user_id)
    document = find_document(doc_id)

    # 2) 사람이나 문서가 없으면 "볼 수 없음"으로 안전하게 답한다(오류로 멈추지 않는다).
    if user is None or document is None:
        return False

    # 3) 실제 "볼 수 있나?" 판단은 기존 함수에 그대로 맡기고, 결과를 그대로 돌려준다.
    return check_search_permission(user, document)


def check_existing_request(user_id: int, doc_id: str) -> bool:
    """M-03 이 사람이 이 문서에 대해 '아직 처리 안 된(대기 중) 요청'을 이미 냈는지 확인한다.

    (대기 중 = 관리자가 아직 허락도 거절도 안 한 상태. 같은 요청을 두 번 내지 않게 막는 데 쓴다.)
    """
    return has_pending_request(user_id, doc_id)


def can_request_access(user_id: int, doc_id: str) -> bool:
    """M-03 이 사람이 이 문서에 '보게 해 주세요' 요청을 '새로' 낼 수 있는지 판단한다.

    다음 중 하나라도 해당하면 요청할 수 없다(False):
      - 최종 관리자(super_admin): 어차피 모든 문서를 볼 수 있어 요청이 필요 없다.
      - 이미 볼 수 있는 문서: 요청할 이유가 없다.
      - 이미 대기 중인 요청이 있음: 같은 요청을 또 낼 필요가 없다.
    셋 다 아니면(= 못 보는 문서인데 요청도 안 낸 상태) 요청할 수 있다(True).
    """
    # 사람·문서를 한 번 찾아 공통 판단(_can_request)에 넘긴다.
    return _can_request(find_user(user_id), find_document(doc_id), user_id, doc_id)


def _can_request(user: dict | None, document: dict | None, user_id: int, doc_id: str) -> bool:
    """요청 가능 여부 공통 판단. 이미 찾아 둔 user·document를 받아 같은 조회를 두 번 하지 않게 한다.

    요청 불가(False): 사람/문서 없음, 최종 관리자(전부 열람 가능), 이미 열람 가능, 이미 대기 중.
    넷 다 아니면 요청 가능(True).
    """
    if user is None or document is None:
        return False
    if user["role"] == ROLE_SUPER_ADMIN:  # 어차피 전부 볼 수 있어 요청 불필요
        return False
    if check_search_permission(user, document):  # 이미 볼 수 있음 → 요청 불필요
        return False
    if has_pending_request(user_id, doc_id):  # 이미 대기 중 → 중복 금지
        return False
    return True


def filter_requestable_documents(user: dict, documents: list[dict]) -> list[dict]:
    """M-03 문서 목록에서 '아직 못 보지만 요청하면 볼 수 있는' 것만 골라 돌려준다 (배치).

    검색 결과처럼 문서가 여러 개일 때, 후보마다 can_request_access를 부르면 문서마다 사용자·승인·
    대기 요청을 다시 조회해 DB 연결이 수십 번 생긴다. 그래서 사용자 승인 내역과 대기 요청을 각각
    '한 번만' 읽고, 각 문서에 열람 매트릭스를 적용한다. 권한 규칙은 여전히 여기(permission_service)
    한 곳에서만 판정한다. documents는 Chroma 메타데이터 모양이어야 한다
    ({doc_id, company_id, access_level, is_group_shared, ...}).
    """
    # 요청 대상이 아닌 경우(어드민은 전부 열람 가능, 알 수 없는 사용자)엔 요청할 문서가 없다.
    if not user or user.get("role") not in ROLES or user["role"] == ROLE_SUPER_ADMIN:
        return []

    user_id = user["id"]
    try:
        approved = get_approved_doc_ids(user_id)      # 승인 문서: 한 번만
        pending = set(get_pending_doc_ids(user_id))   # 대기 요청: 한 번만
        conditions = _allowed_conditions(user, approved_doc_ids=approved)  # DB 재조회 없음
    except PermissionError:
        return []

    requestable: list[dict] = []
    seen: set = set()
    for document in documents:
        doc_id = document.get("doc_id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        if doc_id in pending:  # 이미 대기 중인 요청이 있으면 제외
            continue
        if any(_matches(condition, document) for condition in conditions):  # 이미 볼 수 있으면 제외
            continue
        requestable.append(document)
    return requestable


def request_document_access(user_id: int, doc_id: str, reason: str) -> bool:
    """M-03 못 보는 문서에 대해 '이래서 보고 싶어요'(사유)를 적어 열람 요청을 남긴다.

    이 요청은 그 문서를 가진 회사의 관리자가 나중에 보고 허락/거절한다(A-05).
    사유가 규칙에 안 맞거나 요청할 수 없는 상황(관리자·이미 열람 가능·대기 중 요청 있음)이면
    아무것도 저장하지 않고 False. 요청을 잘 남기면 A-04 감사 로그에 남기고 True.
    """
    # 1) 사유가 규칙(5~500자)에 맞는지 먼저 본다 (형식 검증은 validators에 있다).
    if not validate_request_reason(reason):
        return False

    # 2) 사람·문서를 한 번만 찾고(중복 조회 방지), 지금 요청해도 되는 상황인지 확인한다.
    user = find_user(user_id)
    document = find_document(doc_id)
    if not _can_request(user, document, user_id, doc_id):
        return False

    # 3) 저장한다. 저장 함수가 '대기 중 요청이 없을 때만' 넣으므로 중복 요청은 걸러진다.
    #    성공하면 새 요청 id, 이미 대기 요청이 있어 못 넣으면 None.
    owner_company = document["company_id"]  # 주인 회사 = 문서를 가진 회사
    request_id = insert_access_request(user_id, doc_id, owner_company, reason.strip())
    if request_id is None:
        return False

    # 4) 성공한 요청을 A-04 감사 로그에 남긴다 (기록이 실패해도 요청은 유효하므로 True).
    _audit_access_request(user_id, doc_id, owner_company, request_id)
    return True


def get_access_request_history(user_id: int) -> list[dict]:
    """M-03 마이페이지용: 이 사용자가 낸 열람 권한 요청 목록(문서·회사·사유·상태·시각)을 최신순으로 돌려준다.

    status는 코드(pending/approved/rejected) 그대로다. 화면에서 한글 이름·색으로 바꾼다.
    """
    return list_access_requests_by_user(user_id)


def _audit_access_request(user_id: int, doc_id: str, owner_company: str, request_id: int) -> None:
    """A-04 권한 요청을 감사 로그에 남긴다. 기록이 실패해도 요청 등록을 되돌리지 않도록 예외는 삼킨다."""
    try:
        record_audit_log(
            user_id,
            "access_request",
            doc_id,
            None,
            False,
            None,
            target_type="document",
            doc_ids=[doc_id],
            doc_companies=[owner_company],
            context_detail={"request_id": request_id},
        )
    except Exception:
        logger.exception("감사 로그 기록 실패(access_request)")
