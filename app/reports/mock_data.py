"""R-02 목(가짜) 데이터. R-01 수집 기능이 완성되면 이 파일을 지운다."""

# ─────────────────────────────────────────────────────────────
# 김소은의 R-01(문서 수집)이 아직 없어서 가짜로 대신하는 것:
#   1) select_section_evidence() ← 섹션별 근거 고르기 (진짜: services/report_collector)
#   2) MOCK_REQUEST, MOCK_COLLECTION ← 확인용 화면·테스트에서 쓸 가짜 조건과 수집 결과
#
# 진짜가 완성되면 report_generator.py의 import 한 줄만 바꾸고 이 파일은 지워요.
# 청크 내용은 모두 지어낸 "가상 자료"예요. 실제 회사 정보가 아니에요.
# ─────────────────────────────────────────────────────────────

from datetime import date

from app.reports.models.report_models import (
    Chunk, CollectionResult, ReportRequest, ReportTemplate, SectionType,
)


def select_section_evidence(section_type: SectionType, collection: CollectionResult) -> list[Chunk]:
    """[임시] 섹션별 근거 선별. 진짜는 김소은이 report_collector에 만든다 (R-01)."""
    # 진짜는 섹션 목적(현황=회사별 사업, 시너지=공통 주제)에 맞게 골라 주지만,
    # 지금은 모아 온 청크를 전부 그대로 돌려줘요.
    return collection.chunks


# 가짜 보고서 생성 조건: "스마트 물류" 주제로 3사 종합 보고서
MOCK_REQUEST = ReportRequest(
    template=ReportTemplate.COMPREHENSIVE,
    topic="스마트 물류",
    company_ids=["ELV", "MVX", "HRI"],  # 회사 코드 (이름은 get_company_names()가 찾아요)
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

# 가짜 수집 결과. text 맨 앞의 [회사 · 제목 · 위치]는 팀 청크 규칙(data-model.md)을 따랐어요.
# metadata 칸 이름도 data-model.md §4(Chroma 메타데이터)와 똑같이 맞췄어요.
#   company_id = 회사 코드(ELV/MVX/HRI). S-04 출처 패널이 이 값으로 회사별 카드를 묶어요.
#   doc_id = 문서 번호(글자). S-05 원문 뷰어가 이 값으로 원문을 찾아요.
#   file_name·location = 출처에 보일 파일명·위치
MOCK_COLLECTION = CollectionResult(
    chunks=[
        Chunk(
            chunk_id="doc-elv#0003",
            text="[현대엘리베이터 · 2025 사업보고서(가상) · p.12] "
                 "물류센터용 고속 화물 승강기 공급을 확대하고 있으며, "
                 "2025년 물류 시설 대상 수주가 전년 대비 증가함.",
            metadata={
                "company_id": "ELV", "company_name": "현대엘리베이터", "doc_id": "doc-elv",
                "title": "2025 사업보고서(가상)", "file_name": "elv_2025_report.pdf",
                "page": 12, "location": "p.12",
            },
        ),
        Chunk(
            chunk_id="doc-mvx#0010",
            text="[현대무벡스 · 2025 반기보고서(가상) · II. 사업의 내용] "
                 "스마트 물류 자동화 설비(자동창고, 컨베이어) 사업을 주력으로 하며, "
                 "물류센터 자동화 수요 증가에 대응해 설비 공급을 늘리고 있음.",
            metadata={
                "company_id": "MVX", "company_name": "현대무벡스", "doc_id": "doc-mvx",
                "title": "2025 반기보고서(가상)", "file_name": "2025 반기보고서(가상)",
                "page": 0, "location": "II. 사업의 내용",
            },
        ),
        Chunk(
            chunk_id="doc-hri#0002",
            text="[현대경제연구원 · 물류산업 전망 보고서(가상) · p.5] "
                 "국내 물류센터의 자동화율은 아직 낮은 수준이며, "
                 "인력난으로 자동화 투자 수요가 계속 늘어날 것으로 전망됨.",
            metadata={
                "company_id": "HRI", "company_name": "현대경제연구원", "doc_id": "doc-hri",
                "title": "물류산업 전망 보고서(가상)", "file_name": "hri_logistics_outlook.pdf",
                "page": 5, "location": "p.5",
            },
        ),
    ],
    empty_companies=[],
)
