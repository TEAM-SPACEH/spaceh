"""R-03·R-04 각주 매핑, 각주 번호 정리, 원문 연결 정보, 섹션 앵커 생성."""

# ─────────────────────────────────────────────────────────────
# 이 파일은 R-03(김소은)과 R-04(박예원)가 같이 써요. (김소은님과 합의)
#   - map_footnotes(), renumber_footnotes(), build_source_link() ..... R-03 (김소은) ← 아직 없음
#   - build_section_anchor() ......................................... R-04 (박예원)
#
# R-03 함수가 생기기 전까지 보고서 전체 번호 매기기는 mock_data.build_mock_report()가 대신해요.
# services 파일이라 화면 코드(st.*)는 쓰지 않아요. (팀 규칙)
# ─────────────────────────────────────────────────────────────
import re
from dataclasses import replace

from app.reports.models.report_models import Chunk, Footnote, Section, SectionType

# 앵커 ID 앞부분. 샘플 양식(정기·감사보고서)의 "#sec-…" 모양을 따랐어요.
SECTION_ANCHOR_PREFIX = "sec-"


def build_section_anchor(section_ref: SectionType) -> str:
    """R-04 요약 항목의 section_ref를 상세보고서 섹션의 앵커 ID로 바꾼다."""
    # 예: SectionType.STATUS → "sec-status"
    # 화면의 섹션 이동, Markdown 파일 안 링크(#sec-status), DOCX 책갈피(R-05)가
    # 모두 같은 ID를 써야 해서 이 한 곳에서만 만들어요. (명세서: "한 곳에서만 만든다")
    # 영어 값(value)을 써서 HTML id·DOCX 책갈피 이름으로 써도 문제가 없어요.
    return f"{SECTION_ANCHOR_PREFIX}{SectionType(section_ref).value}"

# 본문에 표시된 [1], [2] 등의 인용 번호를 찾는 정규식
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def map_footnotes(
    sections: list[Section],
    chunks: list[Chunk],
) -> tuple[list[Section], list[Footnote]]:
    """섹션별 인용 번호를 실제 청크와 연결하고 보고서 전체 각주를 생성한다."""

    # 수집된 근거 청크만 인용할 수 있도록 확인
    allowed_chunk_ids = {chunk.chunk_id for chunk in chunks}

    # 청크 ID별로 부여한 보고서 전체 각주 번호
    chunk_numbers = {}

    footnotes = []
    mapped_sections = []

    for section in sections:
        # 근거가 없는 섹션은 그대로 유지
        if not section.has_evidence:
            mapped_sections.append(replace(section))
            continue

        # 현재 섹션의 로컬 번호 → 전체 각주 번호
        local_numbers = {}

        def replace_citation(match):
            local_num = int(match.group(1))
            index = local_num - 1

            # 실제 근거 청크가 없는 번호는 제거
            if index < 0 or index >= len(section.evidence):
                return ""

            chunk = section.evidence[index]

            # 수집된 근거에 포함되지 않은 청크는 제외
            if chunk.chunk_id not in allowed_chunk_ids:
                return ""

            # 같은 청크가 이미 인용되었다면 기존 번호 재사용
            if chunk.chunk_id not in chunk_numbers:
                number = len(footnotes) + 1
                chunk_numbers[chunk.chunk_id] = number

                # R-02에서 만들어 둔 출처 정보 활용
                source = (
                    section.sources[index]
                    if index < len(section.sources)
                    else {}
                )
                metadata = chunk.metadata or {}

                # 청크 앞머리의 [회사 · 제목 · 위치] 제거
                quote = re.sub(
                    r"^\s*\[[^\]\n]+\]\s*",
                    "",
                    chunk.text,
                    count=1,
                )
                quote = " ".join(quote.split())

                # 인용 문장은 최대 150자로 제한
                if len(quote) > 150:
                    quote = quote[:150] + "…"

                footnotes.append(
                    Footnote(
                        number=number,
                        company=source.get("company") or metadata.get("company", ""),
                        company_id=source.get("company_id") or metadata.get("company_id", ""),
                        filename=source.get("filename") or metadata.get("filename", ""),
                        location=source.get("location") or metadata.get("location", ""),
                        quote=quote,
                        text=chunk.text,
                        doc_id=str(source.get("doc_id") or metadata.get("doc_id", "")),
                        chunk_id=chunk.chunk_id,
                    )
                )

            global_num = chunk_numbers[chunk.chunk_id]
            local_numbers[local_num] = global_num

            return f"[{global_num}]"

        # 섹션 본문에 있는 인용 번호 변환
        new_body = CITATION_PATTERN.sub(
            replace_citation,
            section.body,
        )

        # 출처 패널의 번호도 본문 번호와 일치시킴
        new_sources = []

        for local_num, global_num in local_numbers.items():
            index = local_num - 1

            if index < len(section.sources):
                source = section.sources[index].copy()
                source["citation_number"] = global_num
                new_sources.append(source)

        mapped_sections.append(
            replace(
                section,
                body=new_body,
                sources=new_sources,
            )
        )

    return mapped_sections, footnotes
