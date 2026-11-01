"""A-07 계열사 화면 테스트. Streamlit AppTest 로 실제 렌더링 결과를 확인하고, 서비스는 가짜로 바꿔 DB 없이 돌린다.

실행: python -m unittest tests.admin.test_company_view
"""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = "app.admin.views.companies.get_companies"
CREATE = "app.admin.views.components.company_form.create_company"
SET_DART = "app.admin.views.components.company_detail.set_dart_code"

SUPER = {"id": 1, "role": "super_admin", "company_id": None}


def _page_app():
    from app.admin.views.companies import render_admin_companies

    render_admin_companies({"id": 1, "role": "super_admin", "company_id": None})


def _admin_app():
    from app.admin.views.companies import render_admin_companies

    render_admin_companies({"id": 2, "role": "company_admin", "company_id": "MVX"})


def _company(company_id="MVX", **overrides):
    company = {
        "company_id": company_id,
        "name": "현대무벡스",
        "dart_code": None,
        "is_active": True,
        "default_share_enabled": False,
        "doc_total": 188,
        "doc_public": 48,
        "doc_internal": 88,
        "doc_confidential": 52,
        "user_count": 2,
    }
    company.update(overrides)
    return company


COMPANIES = [
    _company("HRI", name="현대경제연구원", doc_total=312, doc_public=190, doc_internal=100, doc_confidential=22, dart_code=None),
    _company("MVX", dart_code="00126380"),
    _company("NEW", name="신규사", doc_total=0, doc_public=0, doc_internal=0, doc_confidential=0, user_count=0, is_active=False),
]


def _html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


class CompanyViewTest(unittest.TestCase):
    def _run(self, app=_page_app, companies=COMPANIES):
        patcher = patch(PAGE, return_value=companies)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock, AppTest.from_function(app).run(timeout=30)

    def _submit(self, at):
        [b for b in at.button if b.label == "계열사 더하기"][0].click().run(timeout=30)

    def test_page_shows_title_table_dart_card_and_form(self):
        """제목·설명·표·DART 연결 카드·계열사 더하기 폼이 그려진다."""
        _, at = self._run()

        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "계열사")
        html_values = _html(at)
        for expected in ("전체 관리", "현대경제연구원", "312", "사용 중", "중지", "문서 없음", "DART 연결", "고유번호 00126380", "고유번호 입력 전", "계열사 더하기"):
            self.assertIn(expected, html_values)
        self.assertTrue(any("바로 필터와 권한 규칙" in c.value for c in at.caption))

    def test_distribution_shows_ratio_bar_with_counts(self):
        """보안 등급 분포는 공개·사내·기밀 비율 막대로 보이고, 막대 설명과 범례에 등급별 수·이름이 있다 (Figma 11)."""
        _, at = self._run(companies=[COMPANIES[0]])
        html_values = _html(at)
        self.assertIn('class="sh-dist"', html_values)
        self.assertIn("공개 190 · 사내 100 · 기밀 22", html_values)
        for legend in ("공개", "사내", "기밀"):
            self.assertIn(legend, html_values)

    def test_form_has_labels_placeholders_and_default_share_off(self):
        """폼 입력칸 이름·예시·기본값(공유 OFF)이 시안과 같다."""
        _, at = self._run()

        self.assertEqual(at.text_input(key="company-form-name").placeholder, "예: 현대투자파트너스")
        self.assertEqual(at.text_input(key="company-form-code").placeholder, "영문 대문자 2–5자, 예: HIP")
        self.assertEqual(at.text_input(key="company-form-dart").placeholder, "상장사만, 8자리")
        self.assertFalse(at.toggle(key="company-form-share").value)
        self.assertIn("사원번호 앞부분으로 쓰여 나중에 바꿀 수 없습니다.", _html(at))

    def test_submit_success_calls_service_clears_form_and_toasts(self):
        """입력 후 제출하면 서비스가 정규화 전 값 그대로 호출되고, 성공 토스트가 뜨며 입력칸이 비워진다."""
        _, at = self._run()
        at.text_input(key="company-form-name").input("현대투자파트너스")
        at.text_input(key="company-form-code").input("hip")
        at.text_input(key="company-form-dart").input("00126380")
        at.toggle(key="company-form-share").set_value(True)
        with patch(CREATE, return_value={"company_id": "HIP", "status": "success", "message": "계열사가 추가되었습니다."}) as create:
            self._submit(at)

        create.assert_called_once_with(SUPER, "현대투자파트너스", "hip", "00126380", True)
        self.assertEqual([t.value for t in at.toast], ["계열사가 추가되었습니다."])
        self.assertEqual(at.text_input(key="company-form-name").value, "")
        self.assertEqual(at.text_input(key="company-form-code").value, "")
        self.assertFalse(at.toggle(key="company-form-share").value)
        self.assertEqual(len(at.error), 0)

    def test_submit_failure_keeps_input_and_shows_service_message(self):
        """서비스가 거부하면 안내 문구가 폼 아래에 보이고, 입력값은 그대로 남는다."""
        _, at = self._run()
        at.text_input(key="company-form-name").input("회사")
        at.text_input(key="company-form-code").input("X")
        with patch(CREATE, side_effect=ValueError("코드는 영문 대문자 2–5자로 입력해 주세요. 예: HIP")):
            self._submit(at)

        self.assertEqual([e.value for e in at.error], ["코드는 영문 대문자 2–5자로 입력해 주세요. 예: HIP"])
        self.assertEqual(at.text_input(key="company-form-name").value, "회사")
        self.assertEqual(len(at.toast), 0)

    def test_unexpected_error_hides_details(self):
        """예상 못 한 오류는 내용을 보이지 않고 일반 안내만 보인다."""
        _, at = self._run()
        with patch(CREATE, side_effect=RuntimeError("secret db detail")), self.assertLogs(
            "app.admin.views.components.company_form", level="ERROR"
        ):
            self._submit(at)

        self.assertEqual([e.value for e in at.error], ["계열사를 추가하지 못했습니다. 잠시 후 다시 시도해 주세요."])

    def test_dart_input_saves_through_service(self):
        """DART 고유번호를 입력하고 저장하면 서비스가 호출되고 토스트가 뜬다."""
        _, at = self._run()
        at.text_input(key="dart-input-HRI-").input("00112233")
        with patch(SET_DART, return_value={"company_id": "HRI", "dart_code": "00112233", "status": "success", "message": "DART 고유번호가 저장되었습니다."}) as setter:
            [b for b in at.button if b.key == "dart-input-HRI--save"][0].click().run(timeout=30)

        setter.assert_called_once_with(SUPER, "HRI", "00112233")
        self.assertEqual([t.value for t in at.toast], ["DART 고유번호가 저장되었습니다."])

    def test_dart_input_failure_shows_message(self):
        """서비스가 거부하면(예: 형식 오류) 안내 문구가 토스트로 보인다."""
        _, at = self._run()
        at.text_input(key="dart-input-HRI-").input("123")
        with patch(SET_DART, side_effect=ValueError("DART 고유번호는 숫자 8자리로 입력해 주세요.")):
            [b for b in at.button if b.key == "dart-input-HRI--save"][0].click().run(timeout=30)

        self.assertEqual([t.value for t in at.toast], ["DART 고유번호는 숫자 8자리로 입력해 주세요."])

    def test_existing_dart_code_is_prefilled_for_edit(self):
        """이미 입력된 고유번호는 입력칸에 채워져 있고, 키에 값이 들어 있어 저장 후 새 값으로 다시 그려진다."""
        _, at = self._run()
        self.assertEqual(at.text_input(key="dart-input-MVX-00126380").value, "00126380")

    def test_untrusted_names_are_escaped(self):
        """회사명에 든 HTML·Markdown 은 해석되지 않고 글자 그대로 나온다."""
        evil = _company("EVL", name="<img src=x onerror=alert(1)> **굵게** [링크](http://example.com)")
        _, at = self._run(companies=[evil])

        self.assertNotIn("<img", _html(at))
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", _html(at))

    def test_empty_list_shows_notice(self):
        """등록된 계열사가 없으면 안내 문구가 나온다."""
        _, at = self._run(companies=[])
        self.assertFalse(at.exception)
        self.assertTrue(any("등록된 계열사가 없습니다" in info.value for info in at.info))

    def test_non_super_admin_is_blocked_before_service_call(self):
        """최종 어드민이 아니면 안내 문구만 보이고 서비스는 호출되지 않는다."""
        mock, at = self._run(app=_admin_app)

        self.assertEqual([e.value for e in at.error], ["최종 어드민만 접근할 수 있는 페이지입니다."])
        mock.assert_not_called()

    def test_list_failure_shows_error_not_traceback(self):
        """목록 조회가 실패하면 일반 안내만 보이고 예외는 화면에 나오지 않는다."""
        mock, _ = self._run()
        mock.side_effect = RuntimeError("db down")
        with self.assertLogs("app.admin.views.companies", level="ERROR"):
            at = AppTest.from_function(_page_app).run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual([e.value for e in at.error], ["계열사 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."])


if __name__ == "__main__":
    unittest.main()
