"""A-04 감사 로그 DB 읽기/쓰기 (repositories 계층).

감사 로그 = "누가·언제·무엇을 했고, 막혔다면 왜 막혔는지"를 audit_logs 테이블에 남기는 기록.
이 파일은 SQL 실행만 맡는다. 관리자 권한 확인·시각 생성·입력 가공은 services 계층
(audit_service)이 하고, 여기서는 이미 정해진 값을 그대로 저장·조회한다.

규칙: SQL 값은 모두 %s 바인딩으로 넘긴다 (f-string 은 고정 SQL 조각을 잇는 데만 쓴다).
"""

import json
from datetime import datetime

from core.database import get_connection

# 조회 시 가져올 컬럼 목록 (고정 문자열이라 f-string 으로 SQL 에 넣어도 안전하다).
# SELECT 컬럼. id 는 서비스 계층에서 log_id 로 이름을 바꿔 쓴다.
_COLUMNS = (
    "id, created_at, user_id, employee_no, role, company_code, action, "
    "target_type, target_id, query, filters, doc_ids, doc_companies, "
    "result_count, is_blocked, block_reason, context_detail"
)
# JSON 컬럼. PyMySQL 은 JSON 을 문자열로 돌려주므로 읽을 때 파싱한다.
_JSON_COLUMNS = ("filters", "doc_ids", "doc_companies", "context_detail")


def _dump(value) -> str | None:
    """파이썬 값(dict/list)을 JSON 컬럼에 넣을 문자열로 바꾼다. None 은 NULL 로 둔다.

    ensure_ascii=False: 한글을 유니코드 이스케이프 문자열로 바꾸지 않고 그대로 저장해 DB 에서도 읽히게 한다.
    default=str: datetime 같은 JSON 으로 못 바꾸는 값이 섞여도 문자열로 바꿔 기록이 실패하지 않게 한다.
    """
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def _decode(row: dict | None) -> dict | None:
    """DB 행의 JSON 컬럼 문자열을 파이썬 값으로 바꾼다 (_dump 의 반대 방향)."""
    if row is None:
        return None
    for column in _JSON_COLUMNS:
        # NULL 은 None 으로 오므로 문자열일 때만 파싱한다.
        if isinstance(row.get(column), (str, bytes)):
            row[column] = json.loads(row[column])
    return row


def insert_log(
    user_id: int | None,
    employee_no: str | None,
    action: str,
    target_type: str | None,
    target_id: str | None,
    query: str | None,
    filters: dict | None,
    doc_ids: list | None,
    doc_companies: list | None,
    result_count: int | None,
    is_blocked: bool,
    block_reason: str | None,
    context_detail: dict | None,
    created_at: datetime,
) -> int:
    """감사 로그 1건을 저장하고 새 id 를 돌려준다.

    사용자 조회와 INSERT 를 한 연결(한 트랜잭션)에서 처리한다. user_id 나 employee_no 로
    users 에서 찾으면 사원번호·역할·소속을 기록 당시 값으로 복사해 둔다. 찾지 못하면
    (존재하지 않는 로그인 ID) user_id 는 NULL, 넘겨받은 employee_no 만 남는다.

    왜 복사해 두나: 나중에 사용자의 역할·소속이 바뀌어도, 감사 로그는
    "그 시점에 누가 했는지"를 그대로 보여 줘야 하기 때문이다.
    IP 주소는 저장하지 않는다 (컬럼 없음).

    인자: user_id 는 users.id (로그인 실패처럼 모르면 None), employee_no 는 id 로 못 찾을 때
    쓰는 로그인 입력 사원번호, action 은 행위 코드(login·search·view_document 등 영어 소문자), target_type·target_id 는
    행위 대상, query·filters 는 검색어·필터, doc_ids·doc_companies 는 관련 문서와 그 계열사,
    is_blocked·block_reason 은 권한 차단 여부와 사유, context_detail 은 부가 정보다.
    filters·doc_ids·doc_companies·context_detail 은 JSON 으로 저장한다.
    created_at 은 호출하는 쪽(서비스)이 KST 로 정해서 넘긴다. 반환값은 새 audit_logs.id.
    """
    with get_connection() as conn, conn.cursor() as cur:
        # 1) 기록할 사용자 정보 찾기: user_id 가 있으면 그것으로, 없으면 사원번호로.
        user_row = None
        if user_id is not None:
            cur.execute(
                "SELECT id, employee_no, role, company_id FROM users WHERE id = %s",
                (user_id,),
            )
            user_row = cur.fetchone()
        elif employee_no:
            cur.execute(
                "SELECT id, employee_no, role, company_id FROM users "
                "WHERE employee_no = %s",
                (employee_no,),
            )
            user_row = cur.fetchone()

        # 찾았으면 users 의 값으로 덮어써서 기록 시점의 사원번호·역할·소속 스냅샷을 만든다.
        if user_row:
            user_id, employee_no = user_row["id"], user_row["employee_no"]
            role, company_code = user_row["role"], user_row["company_id"]
        else:
            # 없는 users.id 를 넣으면 외래키 오류로 기록 자체가 사라지므로 NULL 로 둔다.
            user_id, role, company_code = None, None, None

        # 2) 로그 저장. JSON 컬럼은 _dump 로 문자열로 바꿔 넣는다. (SELECT 와 같은 연결이라
        #    사용자 조회~INSERT 사이에 값이 어긋나지 않는다.)
        cur.execute(
            "INSERT INTO audit_logs "
            "(created_at, user_id, employee_no, role, company_code, action, "
            "target_type, target_id, query, filters, doc_ids, doc_companies, "
            "result_count, is_blocked, block_reason, context_detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                created_at,
                user_id,
                employee_no,
                role,
                company_code,
                action,
                target_type,
                target_id,
                query,
                _dump(filters),
                _dump(doc_ids),
                _dump(doc_companies),
                result_count,
                is_blocked,
                block_reason,
                _dump(context_detail),
            ),
        )
        # 방금 INSERT 한 행의 id.
        return cur.lastrowid


def _where(
    company_code: str | None,
    employee_no: str | None = None,
    action: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    blocked_only: bool = False,
) -> tuple[str, list]:
    """조건이 있는 것만 AND 로 잇는다. SQL 문자열은 고정 조각이고 값은 params 로만 간다.

    Returns:
        (" WHERE ..." 문자열, %s 에 대응하는 값 리스트). 조건이 하나도 없으면 ("", []).
        company_code 가 None 이면 계열사 제한 없음 = 전체 조회(super_admin 용).

    계열사 범위(company_code 를 준 경우)의 뜻: 행동한 사람의 소속이 그 계열사인 로그만.
    결과·근거 문서에 그 계열사 문서가 들어 있어도 행동한 사람이 타사 직원이면 포함하지 않는다
    (타사 직원의 검색어·질문 원문이 노출되지 않게 한다). company_code 는 행동 당시 소속이다.
    """
    clauses: list[str] = []
    params: list = []
    if company_code is not None:
        # 소속을 알 수 없는 로그(로그인 실패 등, company_code 가 NULL)는 어느 계열사 것인지 알 수 없어
        # 계열사 관리자 범위에 들어오지 않는다. 최종 어드민(company_code=None)만 본다.
        clauses.append("company_code = %s")
        params.append(company_code)
    if employee_no:
        clauses.append("employee_no = %s")
        params.append(employee_no)
    if action:
        clauses.append("action = %s")
        params.append(action)
    if start is not None:
        clauses.append("created_at >= %s")
        params.append(start)
    if end is not None:
        # 종료 시각은 '미만'이다. 서비스가 종료일 다음 날 0시를 넘겨 종료일 당일까지 포함시킨다.
        clauses.append("created_at < %s")
        params.append(end)
    if blocked_only:
        # 값이 없는 고정 조건이라 바인딩할 params 는 추가하지 않는다.
        clauses.append("is_blocked = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def search_logs(
    company_code: str | None,
    employee_no: str | None,
    action: str | None,
    start: datetime | None,
    end: datetime | None,
    blocked_only: bool,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """조건에 맞는 로그를 최신순으로 한 페이지 읽고, 조건 전체 건수를 함께 돌려준다.

    limit·offset 은 페이지 크기와 건너뛸 건수다. 돌려주는 전체 건수는 페이지와 무관하게
    조건 전체 기준이며, 화면의 "총 N건"·페이지 수 계산에 쓴다.
    """
    where, params = _where(company_code, employee_no, action, start, end, blocked_only)
    with get_connection() as conn, conn.cursor() as cur:
        # 전체 건수와 페이지 목록을 같은 조건으로 따로 조회한다.
        cur.execute(f"SELECT COUNT(*) AS cnt FROM audit_logs{where}", params)
        total = cur.fetchone()["cnt"]
        cur.execute(
            f"SELECT {_COLUMNS} FROM audit_logs{where} "
            # 같은 시각의 로그도 순서가 흔들리지 않게 id 를 보조 정렬 키로 쓴다.
            "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cur.fetchall()
    return [_decode(row) for row in rows], total


def get_log(log_id: int, company_code: str | None) -> dict | None:
    """로그 1건. company_code 를 주면 그 계열사 범위(_where 참고)의 로그만 찾는다 (없으면 None).

    범위 밖 로그의 id 를 넣어도 조회되지 않게 id 조건에 계열사 조건을 함께 건다.
    """
    where, params = _where(company_code)
    clause = f"{where} AND id = %s" if where else " WHERE id = %s"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM audit_logs{clause}", [*params, log_id])
        return _decode(cur.fetchone())


def list_recent(company_code: str | None, limit: int) -> list[dict]:
    """최근 로그 limit 건 (대시보드용). company_code 가 None 이면 전체 계열사."""
    where, params = _where(company_code)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM audit_logs{where} "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            [*params, limit],
        )
        return [_decode(row) for row in cur.fetchall()]


def list_employee_nos(company_code: str | None) -> list[str]:
    """로그에 등장한 사원번호 목록 (필터 선택지). 사용자를 알 수 없는 로그는 뺀다.

    company_code 범위(_where 참고) 안의 로그에 등장한 사원번호만 모은다. 범위 밖 로그에만
    나온 사원번호는 선택지에 나오지 않는다.
    """
    where, params = _where(company_code)
    clause = f"{where} AND employee_no IS NOT NULL" if where else " WHERE employee_no IS NOT NULL"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT employee_no FROM audit_logs{clause} ORDER BY employee_no",
            params,
        )
        return [row["employee_no"] for row in cur.fetchall()]


def list_actions(company_code: str | None) -> list[str]:
    """로그에 등장한 행위 코드 목록 (필터 선택지). company_code 범위 안에서만 모은다."""
    where, params = _where(company_code)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT action FROM audit_logs{where} ORDER BY action", params
        )
        return [row["action"] for row in cur.fetchall()]


def lookup_user_names(user_ids: list[int]) -> dict[int, str]:
    """users.id 목록에 대응하는 이름을 {id: 이름} 으로 돌려준다. 목록이 비어 있으면 DB 를 읽지 않는다.

    감사 로그 표에 사원번호 대신 이름을 보여 주려고 쓴다. 로그에는 사용자 id·사원번호만 저장되기 때문이다.
    """
    if not user_ids:
        return {}
    marks = ", ".join(["%s"] * len(user_ids))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id, name FROM users WHERE id IN ({marks})", list(user_ids))
        return {row["id"]: row["name"] for row in cur.fetchall()}


def lookup_documents(doc_ids: list[str]) -> dict[str, dict]:
    """doc_id 목록에 대응하는 문서 제목·소유 회사를 {doc_id: {"title", "company_id"}} 로 돌려준다.

    이미 삭제된 문서는 결과에 없다. 회사를 함께 돌려주는 이유는, 서비스가 "관리자가 볼 수 있는 회사의 문서"만
    제목을 보여 주도록 판단할 수 있게 하기 위해서다 (판단은 여기서 하지 않는다).
    """
    if not doc_ids:
        return {}
    marks = ", ".join(["%s"] * len(doc_ids))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT doc_id, title, company_id FROM documents WHERE doc_id IN ({marks})", list(doc_ids))
        return {row["doc_id"]: {"title": row["title"], "company_id": row["company_id"]} for row in cur.fetchall()}


def get_company_name(company_id: str) -> str | None:
    """계열사 코드의 회사명. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM companies WHERE company_id = %s", (company_id,))
        row = cur.fetchone()
        return row["name"] if row else None


def summarize(company_code: str | None, start: datetime, end: datetime) -> dict:
    """[start, end) 기간의 로그를 company_code 범위(_where 참고) 안에서 집계한다.

    반환: {"total": 전체 건수, "blocked": 차단 건수, "blocked_reasons": [(사유, 건수), ...] 많은 순 최대 3개,
           "downloads": 원문 내려받기 건수, "blocked_downloads": 그중 차단된 건수, "hourly": {시(0~23): 건수}}
    사유가 비어 있는 차단은 "사유 없음"으로 묶는다. 값은 모두 %s 바인딩으로 넘긴다.
    """
    where, params = _where(company_code, start=start, end=end)
    # _where 가 만든 WHERE 에 조건을 더 붙이는 도우미. WHERE 가 이미 있으면 AND, 없으면 WHERE 로 잇는다.
    more = lambda extra: f"{where} AND {extra}" if where else f" WHERE {extra}"  # noqa: E731
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS cnt FROM audit_logs{where}", params)
        total = cur.fetchone()["cnt"]
        cur.execute(f"SELECT COUNT(*) AS cnt FROM audit_logs{more('is_blocked = 1')}", params)
        blocked = cur.fetchone()["cnt"]
        cur.execute(
            f"SELECT COALESCE(NULLIF(block_reason, ''), '사유 없음') AS reason, COUNT(*) AS cnt "
            f"FROM audit_logs{more('is_blocked = 1')} GROUP BY reason ORDER BY cnt DESC, reason LIMIT 3",
            params,
        )
        reasons = [(row["reason"], row["cnt"]) for row in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS cnt FROM audit_logs{more('action = %s')}", [*params, "download"])
        downloads = cur.fetchone()["cnt"]
        cur.execute(
            f"SELECT COUNT(*) AS cnt FROM audit_logs{more('action = %s AND is_blocked = 1')}", [*params, "download"]
        )
        blocked_downloads = cur.fetchone()["cnt"]
        cur.execute(
            f"SELECT HOUR(created_at) AS hr, COUNT(*) AS cnt FROM audit_logs{where} GROUP BY hr", params
        )
        hourly = {row["hr"]: row["cnt"] for row in cur.fetchall()}
    return {
        "total": total,
        "blocked": blocked,
        "blocked_reasons": reasons,
        "downloads": downloads,
        "blocked_downloads": blocked_downloads,
        "hourly": hourly,
    }
