"""report_form(R-01 새 보고서 화면)의 화면 밖으로 꺼낼 수 있는 부분 테스트: 입력 검사, 근거 문서 카드, 목차, 안내 문구.

실행: python -m unittest tests.reports.test_report_form

화면 자체(Streamlit)는 띄워서 확인한다. 여기서는 데이터가 HTML로 안전하게 바뀌는지와 입력 검사를 본다.
"""

import unittest
from datetime import date

from app.reports.models.report_models import ReportTemplate
from app.reports.views import report_form as form

NAMES = {"HRI": "현대경제연구원", "MVX": "현대무벡스", "ELV": "현대엘리베이터"}
JULY = date(2025, 7, 1)
OCTOBER = date(2025, 10, 31)


class ValidateTest(unittest.TestCase):

    def test_valid_input_has_no_error(self):
        self.assertEqual(form._validate("스마트 물류", ["HRI"], JULY, OCTOBER), [])

    def test_blank_topic_is_rejected(self):
        self.assertEqual(form._validate("   ", ["HRI"], JULY, OCTOBER), ["주제를 입력해 주세요."])

    def test_no_company_is_rejected(self):
        self.assertEqual(form._validate("주제", [], JULY, OCTOBER), ["계열사를 하나 이상 선택해 주세요."])

    def test_start_after_end_is_rejected(self):
        self.assertEqual(form._validate("주제", ["HRI"], OCTOBER, JULY), ["시작일이 끝 날짜보다 늦을 수 없습니다."])

    def test_every_problem_is_reported_at_once(self):
        self.assertEqual(len(form._validate("", [], OCTOBER, JULY)), 3)


class EvidenceHtmlTest(unittest.TestCase):

    def test_total_and_per_company_counts(self):
        out = form._evidence_html(["HRI", "MVX", "ELV"], NAMES, {"HRI": 5, "MVX": 7, "ELV": 0})

        self.assertIn("12건", out)
        self.assertIn("5건", out)
        self.assertIn("width:41.7%", out)  # 5 / 12
        self.assertIn("width:58.3%", out)  # 7 / 12

    def test_company_without_documents_gets_warning(self):
        out = form._evidence_html(["HRI", "ELV"], NAMES, {"HRI": 5, "ELV": 0})

        self.assertIn("현대엘리베이터는 이 기간에 볼 수 있는 문서가 없어", out)
        self.assertIn("sh-r-zero", out)

    def test_no_warning_when_every_company_has_documents(self):
        out = form._evidence_html(["HRI"], NAMES, {"HRI": 3})

        self.assertNotIn("sh-r-warn", out)

    def test_all_zero_does_not_divide_by_zero(self):
        out = form._evidence_html(["HRI"], NAMES, {"HRI": 0})

        self.assertIn("0건", out)
        self.assertIn("width:0.0%", out)

    def test_unknown_counts_show_dash_instead_of_a_number(self):
        out = form._evidence_html(["HRI"], NAMES, None)

        self.assertIn("-건", out)
        self.assertIn("불러오지 못했습니다", out)

    def test_no_company_selected_asks_to_choose(self):
        self.assertIn("회사를 고르고", form._evidence_html([], NAMES, None))

    def test_company_name_is_escaped(self):
        out = form._evidence_html(["X"], {"X": "<img src=x onerror=alert(1)>"}, {"X": 0})

        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;img", out)


class OutlineAndNoteTest(unittest.TestCase):

    def test_comprehensive_outline_follows_section_order(self):
        out = form._outline_html(ReportTemplate.COMPREHENSIVE)

        for line in ("1. 개요", "2. 계열사별 현황", "3. 협력 기회와 시너지", "4. 제언", "각주, 근거 문서 목록"):
            self.assertIn(line, out)

    def test_quarterly_outline_has_performance_instead_of_status(self):
        out = form._outline_html(ReportTemplate.QUARTERLY)

        self.assertIn("2. 실적 비교", out)
        self.assertNotIn("현황", out)

    def test_note_does_not_claim_a_number_when_counts_unknown(self):
        self.assertEqual(form._note_text({"HRI": 5, "MVX": 7}), "문서 12건을 읽고 섹션별로 작성합니다.")
        self.assertNotIn("건을", form._note_text(None))


if __name__ == "__main__":
    unittest.main()
