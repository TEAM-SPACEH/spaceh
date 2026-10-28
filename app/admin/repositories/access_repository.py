"""A-03 그룹사 공유 DB·Chroma 읽기/쓰기 (repositories 계층).

이 파일은 SQL 실행과 Chroma 메타데이터 갱신만 맡는다. 누가 바꿀 수 있는지(관리 권한)와
어떤 등급을 공유할 수 있는지는 services 계층(access_service)이 판단하고, 여기서는 받은 값을 그대로 쓴다.

규칙: SQL 값은 모두 %s 바인딩으로 넘긴다 (f-string 은 고정 SQL 조각을 잇는 데만 쓴다).
"""

import logging
from datetime import datetime

from chromadb.errors import NotFoundError

from core import config
from core.chroma import open_chroma_client
from core.database import get_connection

logger = logging.getLogger(__name__)

# 목록 SELECT 컬럼 (고정 문자열이라 f-string 으로 SQL 에 넣어도 안전하다).
_LIST_COLUMNS = (
    "doc_id, company_id, title, file_name, file_format, doc_type, access_level, "
    "is_group_shared, chunk_count, index_status, created_at"
)


def _escape_like(text: str) -> str:
    """LIKE 패턴에서 특별한 뜻을 가진 문자(% _ \\)를 글자 그대로 찾도록 이스케이프한다."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_documents(
    access_levels: tuple[str, ...],
    company_id: str | None,
    keyword: str,
    is_group_shared: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """공유 설정 대상 문서를 최신순으로 한 페이지 조회한다.

    access_levels: 조회할 보안 등급 목록 (비어 있으면 안 된다)
    company_id: 이 회사 문서만 조회. None 이면 전체 회사
    keyword: 제목이나 파일명에 포함된 글자. 빈 문자열이면 조건을 걸지 않는다
    is_group_shared: True/False 면 그 공유 상태만, None 이면 전체
    반환: (행 목록, 조건에 맞는 전체 건수)
    """
    # WHERE 조건을 "조각"으로 모았다가 AND 로 잇는다. 조각 문자열은 모두 코드에 고정된 글자이고,
    # 사용자가 입력한 값(회사·검색어 등)은 %s 자리에 params 로만 넘긴다 (SQL 주입 방지: 입력값이
    # SQL 문장으로 해석되지 않고 값으로만 취급된다).
    # IN (%s, %s) 의 %s 개수는 등급 개수에 맞춰 만든다.
    conditions = ["access_level IN (" + ", ".join(["%s"] * len(access_levels)) + ")"]
    params: list = list(access_levels)
    if company_id:
        conditions.append("company_id = %s")
        params.append(company_id)
    if keyword:
        # 앞뒤 %는 "아무 글자나 와도 됨"이라는 LIKE 의 뜻이다. 사용자가 입력한 % 는 _escape_like 로 막는다.
        # OR 조건은 괄호로 묶어, 뒤에 AND 로 붙는 다른 조건(회사·공유 상태)과 섞이지 않게 한다.
        conditions.append("(title LIKE %s OR file_name LIKE %s)")
        pattern = f"%{_escape_like(keyword)}%"
        params.extend([pattern, pattern])
    if is_group_shared is not None:
        # False 도 "공유 OFF 만 보기"라는 유효한 조건이라 `if is_group_shared:` 가 아니라 None 인지로 구분한다.
        conditions.append("is_group_shared = %s")
        params.append(int(is_group_shared))
    where = " AND ".join(conditions)

    with get_connection() as conn, conn.cursor() as cur:
        # 전체 건수(페이지 수 계산용)와 한 페이지 분량을 같은 연결에서 읽는다.
        cur.execute(f"SELECT COUNT(*) AS total FROM documents WHERE {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT {_LIST_COLUMNS} FROM documents WHERE {where} "
            "ORDER BY created_at DESC, doc_id LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        return list(cur.fetchall()), total


def count_share_status(company_id: str | None) -> dict:
    """공유 설정 화면 요약 카드용 집계: 사내 문서의 공유 ON·OFF 건수와 기밀 문서 건수.

    company_id: 이 회사 문서만 센다. None 이면 전체 회사
    반환: {"shared": 공유 ON(internal), "unshared": 공유 OFF(internal), "confidential": 공유 불가(confidential)}
    """
    where = "WHERE company_id = %s" if company_id else ""
    params = [company_id] if company_id else []
    with get_connection() as conn, conn.cursor() as cur:
        # 한 번의 조회로 세 값을 센다. 값이 하나도 없으면 SUM 이 NULL 이라 COALESCE 로 0 을 준다.
        cur.execute(
            "SELECT "
            "COALESCE(SUM(access_level = 'internal' AND is_group_shared = 1), 0) AS shared, "
            "COALESCE(SUM(access_level = 'internal' AND is_group_shared = 0), 0) AS unshared, "
            "COALESCE(SUM(access_level = 'confidential'), 0) AS confidential "
            f"FROM documents {where}",
            params,
        )
        row = cur.fetchone()
    return {key: int(row[key]) for key in ("shared", "unshared", "confidential")}


def get_document(doc_id: str) -> dict | None:
    """공유 변경 전 확인에 필요한 문서 1건(doc_id·company_id·access_level·is_group_shared)을 읽는다. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, company_id, access_level, is_group_shared FROM documents WHERE doc_id = %s",
            (doc_id,),
        )
        return cur.fetchone()


def get_company_name(company_id: str) -> str | None:
    """계열사 코드의 회사명. 없으면 None."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM companies WHERE company_id = %s", (company_id,))
        row = cur.fetchone()
        return row["name"] if row else None


def list_company_ids() -> list[str]:
    """사용 중인 계열사 코드를 코드순으로 돌려준다 (최종 어드민 계열사 선택지용)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT company_id FROM companies WHERE is_active = 1 ORDER BY company_id")
        return [row["company_id"] for row in cur.fetchall()]


def update_group_share(doc_id: str, share_enabled: bool, user_id: int | None, shared_at: datetime) -> None:
    """MySQL documents 와 Chroma 청크 메타데이터의 공유 값을 함께 바꾼다 (overview §2.3-5).

    Chroma 갱신을 MySQL 커밋 전에 하므로, Chroma 가 실패하면 예외가 get_connection 까지 올라가
    MySQL 도 롤백된다. 둘 중 하나만 바뀐 채로 남지 않게 하려는 것이다.
    shared_by·shared_at 은 "공유를 마지막으로 바꾼 사용자·시각"이다 (감사 로그와 별개로 문서에 남는다).
    """
    # 트랜잭션: get_connection 의 with 블록 안의 SQL 은 "한 묶음"이다. 블록이 정상 종료되면 commit(저장 확정),
    # 중간에 예외가 나면 rollback(없던 일로 되돌림)된다.
    with get_connection() as conn, conn.cursor() as cur:
        # MySQL 의 TINYINT(1) 컬럼에는 True/False 대신 1/0 을 넣는다.
        cur.execute(
            "UPDATE documents SET is_group_shared = %s, shared_by = %s, shared_at = %s WHERE doc_id = %s",
            (int(share_enabled), user_id, shared_at, doc_id),
        )
        # 이 호출이 예외를 내면 위 UPDATE 도 rollback 된다. 순서를 바꿔 Chroma 를 먼저 바꾸면
        # MySQL 이 실패했을 때 Chroma 를 되돌릴 방법이 없다.
        _sync_chroma(doc_id, share_enabled)


def _sync_chroma(doc_id: str, share_enabled: bool) -> None:
    """Chroma 에 있는 이 문서의 모든 청크에 is_group_shared 를 반영한다.

    아직 색인 전이라 컬렉션이나 청크가 없으면 바꿀 것이 없으므로 넘어간다. 색인 때는 MySQL 값을 읽어 넣는다.
    """
    # Chroma = 문서를 청크(잘게 나눈 조각)로 저장하는 벡터 DB. 검색할 때는 MySQL 이 아니라 각 청크에 붙은
    # 메타데이터(회사·등급·공유 여부)로 권한을 거른다 (S-03). 그래서 MySQL 만 바꾸면 검색에는 반영되지 않는다.
    # 클라이언트는 직접 만들지 않고 open_chroma_client() 로만 연다 (Windows 파일 잠금 방지, core/chroma.py).
    with open_chroma_client() as client:
        try:
            collection = client.get_collection(config.CHROMA_COLLECTION)
        except NotFoundError:
            # 여기서 컬렉션을 만들면 I-02 가 정할 설정과 어긋날 수 있어 만들지 않는다.
            logger.warning("Chroma 컬렉션 '%s'이 없어 공유 값 갱신을 건너뜁니다.", config.CHROMA_COLLECTION)
            return
        # include=[] : 청크 본문·벡터는 필요 없고 ID 만 필요하므로 가져오지 않는다.
        chunk_ids = collection.get(where={"doc_id": doc_id}, include=[])["ids"]
        if not chunk_ids:
            return
        # update 는 넘긴 키만 덮어쓰므로 다른 메타데이터(회사·등급 등)는 그대로 남는다.
        collection.update(
            ids=chunk_ids,
            metadatas=[{"is_group_shared": bool(share_enabled)}] * len(chunk_ids),
        )
