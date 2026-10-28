"""A-07 계열사 DB 읽기/쓰기 (repositories 계층).

이 파일은 SQL 실행만 맡는다. 누가 할 수 있는지(최종 어드민)와 값의 형식은 services·validators 가 확인하고,
여기서는 받은 값을 그대로 쓴다. 규칙: SQL 값은 모두 %s 바인딩으로 넘긴다.
"""

import pymysql

from core.database import get_connection


class DuplicateCompanyError(Exception):
    """계열사 등록·수정이 UNIQUE·PRIMARY KEY 제약에 걸렸을 때. kind 는 어느 값이 겹쳤는지다.

    kind: "company_id"(회사 코드) / "name"(회사명) / "dart_code"(DART 고유번호)
    """

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def list_companies() -> list[dict]:
    """계열사 전체를 문서·사용자 수와 함께 돌려준다 (등록 순서, 같으면 코드순).

    반환 행: company_id, name, dart_code, is_active, default_share_enabled,
        doc_total(문서 수), doc_public·doc_internal·doc_confidential(보안 등급별 문서 수), user_count(사용 중인 사용자 수)
    문서·사용자가 하나도 없는 회사도 0 으로 나온다(LEFT JOIN + COALESCE).
    """
    # 문서·사용자는 회사별로 먼저 집계(GROUP BY)한 뒤 붙인다. 회사마다 따로 세는 서브쿼리보다 한 번에 읽는다.
    # SUM(조건) 은 조건이 참인 행만 센다 (MySQL 에서 참=1). 값이 없으면 NULL 이라 COALESCE 로 0 을 준다.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.company_id, c.name, c.dart_code, c.is_active, c.default_share_enabled,
                   COALESCE(d.total, 0) AS doc_total,
                   COALESCE(d.public_cnt, 0) AS doc_public,
                   COALESCE(d.internal_cnt, 0) AS doc_internal,
                   COALESCE(d.confidential_cnt, 0) AS doc_confidential,
                   COALESCE(u.cnt, 0) AS user_count
            FROM companies c
            LEFT JOIN (
                SELECT company_id, COUNT(*) AS total,
                       SUM(access_level = 'public') AS public_cnt,
                       SUM(access_level = 'internal') AS internal_cnt,
                       SUM(access_level = 'confidential') AS confidential_cnt
                FROM documents GROUP BY company_id
            ) d ON d.company_id = c.company_id
            LEFT JOIN (
                SELECT company_id, COUNT(*) AS cnt FROM users WHERE is_active = 1 GROUP BY company_id
            ) u ON u.company_id = c.company_id
            ORDER BY c.created_at, c.company_id
            """
        )
        rows = cur.fetchall()
    # SUM·COUNT 는 Decimal 로 올 수 있어 화면·서비스가 쓰기 쉽게 정수로 바꾼다.
    count_keys = ("doc_total", "doc_public", "doc_internal", "doc_confidential", "user_count")
    return [{**row, **{key: int(row[key]) for key in count_keys}} for row in rows]


def list_active_company_options() -> list[dict]:
    """사용 중인 계열사의 {"id": 코드, "name": 회사명} 목록 (검색 필터 등 선택지용, 코드순)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT company_id, name FROM companies WHERE is_active = 1 ORDER BY company_id")
        return [{"id": row["company_id"], "name": row["name"]} for row in cur.fetchall()]


def get_company(company_id: str) -> dict | None:
    """계열사 1건(company_id·name·dart_code·is_active·default_share_enabled). 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT company_id, name, dart_code, is_active, default_share_enabled FROM companies WHERE company_id = %s",
            (company_id,),
        )
        return cur.fetchone()


def insert_company(company_id: str, name: str, dart_code: str | None, default_share_enabled: bool) -> None:
    """계열사를 등록한다. 코드·회사명·DART 고유번호가 이미 있으면 DuplicateCompanyError."""
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO companies (company_id, name, dart_code, default_share_enabled) VALUES (%s, %s, %s, %s)",
                (company_id, name, dart_code, int(default_share_enabled)),
            )
        except pymysql.err.IntegrityError as exc:
            raise _to_duplicate(exc) from exc


def update_dart_code(company_id: str, dart_code: str | None) -> None:
    """계열사의 DART 고유번호를 바꾼다 (None 이면 비운다). 다른 계열사가 쓰는 번호면 DuplicateCompanyError."""
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute("UPDATE companies SET dart_code = %s WHERE company_id = %s", (dart_code, company_id))
        except pymysql.err.IntegrityError as exc:
            raise _to_duplicate(exc) from exc


def _to_duplicate(exc: pymysql.err.IntegrityError) -> Exception:
    """중복 키 오류(1062)를 어느 값이 겹쳤는지 담은 DuplicateCompanyError 로 바꾼다. 그 밖의 무결성 오류는 그대로 올린다."""
    if exc.args and exc.args[0] == 1062:
        message = str(exc)
        # MySQL 은 오류 문구에 걸린 키 이름을 넣는다 (8.0.19 이후에는 'companies.' 접두어가 붙는다).
        if "uq_companies_name" in message:
            return DuplicateCompanyError("name")
        if "uq_companies_dart_code" in message:
            return DuplicateCompanyError("dart_code")
        if "PRIMARY" in message:
            return DuplicateCompanyError("company_id")
    return exc
