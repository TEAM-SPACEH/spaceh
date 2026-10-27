"""I-02 공통 메타데이터 구성."""

from datetime import date, datetime
from pathlib import Path


def build_metadata(
    doc_id: str, document_info: dict, extracted_info: dict,
) -> dict:
    """I-02 등록 정보와 원문 위치를 검증해 검색용 메타데이터로 매핑한다."""
    # 권한 값은 등록 정보에서만 받으며 추출 텍스트로 추정하거나 덮어쓰지 않는다.
    metadata = {"doc_id": doc_id}
    for key, limit in {"company_id": 20, "company_name": 100,
                       "file_name": 255}.items():
        value = document_info.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"{key} 값이 없거나 올바른 문자열이 아닙니다.")
        metadata[key] = value.strip()
    if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 100:
        raise ValueError("문서 ID가 없거나 올바른 문자열이 아닙니다.")
    if metadata["company_id"] != metadata["company_id"].upper():
        raise ValueError("회사 코드는 등록된 대문자 코드로 지정해야 합니다.")
    if any(separator in metadata["file_name"] for separator in ("/", "\\")):
        raise ValueError("file_name에는 경로가 아닌 파일명만 지정해야 합니다.")

    choices = {
        "doc_type": {"report", "disclosure", "manual", "spec", "intro", "memo"},
        "access_level": {"public", "internal", "confidential"},
        "file_format": {"pdf", "docx", "pptx", "xlsx", "hwp", "dart_xml"},
        "source_type": {"internal", "dart"},
    }
    for key, allowed in choices.items():
        default = "internal" if key == "source_type" else None
        value = document_info.get(key, default)
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"지원하지 않는 {key} 값입니다.")
        metadata[key] = value

    shared = document_info.get("is_group_shared")
    # PyMySQL의 TINYINT(1)는 정수로 반환될 수 있지만 문자열 '0'은 허용하지 않는다.
    if type(shared) not in (bool, int) or shared not in (0, 1):
        raise ValueError("공유 여부는 bool 또는 정수 0·1이어야 합니다.")
    if shared and metadata["access_level"] != "internal":
        raise ValueError("그룹사 공유는 internal 문서만 가능합니다.")
    metadata["is_group_shared"] = bool(shared)

    # 제목은 파일명으로 대체하되 작성일은 등록 정보의 날짜만 사용한다.
    title = document_info.get("title")
    if title is not None and not isinstance(title, str):
        raise ValueError("문서 제목은 문자열이어야 합니다.")
    title = (title or "").strip() or Path(metadata["file_name"]).stem
    if not title or len(title) > 500:
        raise ValueError("문서 제목은 1~500자여야 합니다.")
    metadata["title"] = title
    published = document_info.get("published_date")
    if published is None or published == "":
        # 재색인한 오늘이 아니라 원래 업로드일을 써야 DB 날짜와 일치한다.
        published = document_info.get("created_at")
        if isinstance(published, str):
            published = datetime.fromisoformat(published)
        if isinstance(published, datetime):
            published = published.date()
    if isinstance(published, str):
        published = date.fromisoformat(published)
    if type(published) is not date:
        raise ValueError("작성일 또는 업로드일(created_at)이 필요합니다. 날짜 형식을 확인하세요.")
    metadata["published_date"] = int(published.strftime("%Y%m%d"))
    url = document_info.get("source_url")
    if url is not None and not isinstance(url, str):
        raise ValueError("출처 주소는 문자열이어야 합니다.")
    metadata["source_url"] = url or ""

    # 문서 공통값을 만들 때는 위치를 비워 두고 청크 생성 시 I-01 위치를 붙인다.
    page = extracted_info.get("page", 0)
    if type(page) is not int or page < 0:
        raise ValueError("위치 번호는 0 이상의 정수여야 합니다.")
    metadata["page"] = page
    for key in ("location", "section", "block_type"):
        value = extracted_info.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"{key} 값은 문자열이어야 합니다.")
        metadata[key] = value
    if metadata["block_type"] not in {"", "text", "table", "title"}:
        raise ValueError("지원하지 않는 블록 유형입니다.")
    return metadata
