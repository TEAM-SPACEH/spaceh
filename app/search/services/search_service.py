"""S-02 검색 필터링 서비스. 사용자가 고른 필터를 검색(Chroma) 조건으로 바꾼다."""


def apply_metadata_filters(filters: dict) -> dict:
    """S-02 기업·문서 유형·기간 선택값을 Chroma where 조건(dict)으로 바꿔 돌려준다.

    "where 조건"이란 검색 DB(Chroma)에게 "이런 문서만 보라"고 알려 주는 필터다.
    검색을 하기 '전에' 이 조건을 걸어 미리 거른다(결과를 받은 뒤 거르지 않는다).

    입력 filters — render_search_filters()가 돌려준 모양:
        {
            "companies": ["HRI", "MVX"],   # 고른 회사 코드
            "doc_types": ["report"],       # 고른 문서 유형 코드
            "date_from": 20250101,         # 시작일(YYYYMMDD 정수) 또는 None
            "date_to": 20251231,           # 종료일(YYYYMMDD 정수) 또는 None
        }

    반환 — Chroma where 조각(dict):
        - 조건이 없으면 빈 dict {} (필터를 걸지 않음)
        - 조건이 1개면 그 조건을 그대로, 2개 이상이면 {"$and": [...]}로 묶는다.
        - 이 조각은 S-03 권한 필터와 '바깥에서' 다시 $and로 합쳐진다.

    오류:
        시작일(date_from)이 종료일(date_to)보다 늦으면 ValueError를 던진다.
    """
    filters = filters or {}
    conditions: list[dict] = []

    # 1) 기업: 고른 회사 코드 중 하나라도 맞으면 통과 ($in = 목록 중 하나)
    companies = _as_list(filters.get("companies"))
    if companies:
        conditions.append({"company_id": {"$in": companies}})

    # 2) 문서 유형: 고른 유형 코드(report 등) 중 하나라도 맞으면 통과
    doc_types = _as_list(filters.get("doc_types"))
    if doc_types:
        conditions.append({"doc_type": {"$in": doc_types}})

    # 3) 기간: 시작일 이상(>=), 종료일 이하(<=). 날짜는 YYYYMMDD 정수로 비교한다.
    #    Chroma는 한 필드에 연산자 하나만 받으므로 시작·종료를 각각 조건으로 넣는다.
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    # 시작일이 종료일보다 늦으면 아무 문서도 못 찾으니, 잘못된 입력으로 보고 바로 알린다.
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError(f"시작일({date_from})이 종료일({date_to})보다 늦습니다.")
    if date_from is not None:
        conditions.append({"published_date": {"$gte": date_from}})
    if date_to is not None:
        conditions.append({"published_date": {"$lte": date_to}})

    # 조건 개수에 따라 돌려주는 모양을 맞춘다.
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _as_list(value) -> list:
    """필터 값을 목록으로 맞춘다. 문자열 하나면 한 항목짜리 목록으로, 빈 값이면 빈 목록으로.

    문자열은 list()로 풀면 글자 단위로 쪼개지므로("HRI" → ["H","R","I"]) 따로 감싼다.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)
