import unittest

from app.common.layout import company_label, header_html, scope_html, scope_lines

EMPLOYEE = {"name": "이물류", "role": "employee", "company_id": "MVX"}
COMPANY_ADMIN = {"name": "최관리", "role": "company_admin", "company_id": "MVX", "company_name": "현대무벡스"}
SUPER_ADMIN = {"name": "윤총괄", "role": "super_admin", "company_id": None}


class CommonLayoutTest(unittest.TestCase):
    def test_company_label_prefers_name(self):
        self.assertEqual(company_label(EMPLOYEE), "MVX")
        self.assertEqual(company_label(COMPANY_ADMIN), "현대무벡스")
        self.assertEqual(company_label(SUPER_ADMIN), "전 계열사")

    def test_header_text_by_role(self):
        """로고 옆·이름 아래 글자 (UI v4): 사원은 소속·사원, 관리자는 관리자·회사 관리자, 최종 어드민."""
        self.assertIn("<span>MVX</span>", header_html(EMPLOYEE))
        self.assertIn(">사원<", header_html(EMPLOYEE))
        self.assertIn("<span>관리자</span>", header_html(COMPANY_ADMIN))
        self.assertIn(">현대무벡스 관리자<", header_html(COMPANY_ADMIN))
        self.assertIn("<span>최종 어드민</span>", header_html(SUPER_ADMIN))

    def test_real_login_session_shows_company_name(self):
        """auth_service.login()이 세션에 넣는 모양 그대로: 회사 이름이 헤더·메뉴 섹션·범위 안내에 나온다."""
        session_user = {
            "id": 4,
            "employee_no": "MVX-0002",
            "name": "최관리",
            "role": "company_admin",
            "company_id": "MVX",
            "company_name": "현대무벡스",
        }
        self.assertEqual(company_label(session_user), "현대무벡스")
        self.assertIn(">현대무벡스 관리자<", header_html(session_user))
        self.assertIn("현대무벡스 문서와 사용자", scope_html(session_user))
        # 최종 어드민은 소속이 없어 회사 이름도 None이다.
        self.assertEqual(company_label({**SUPER_ADMIN, "company_name": None}), "전 계열사")

    def test_header_escapes_db_values(self):
        out = header_html({"name": "<b>[x](http://e)</b>", "role": "employee", "company_id": "<i>"})
        self.assertNotIn("<i>", out)
        self.assertNotIn("<b>[x]", out)
        self.assertIn("[x](http://e)", out)

    def test_scope_by_role(self):
        self.assertEqual(scope_lines(EMPLOYEE)[0], "내 열람 범위")
        self.assertIn("MVX 사내 문서", scope_lines(EMPLOYEE)[1])
        self.assertIn("현대무벡스 문서와 사용자", scope_lines(COMPANY_ADMIN)[1])
        self.assertEqual(scope_lines(SUPER_ADMIN), ("관리 범위", ["모든 계열사 문서와 사용자"]))
        self.assertNotIn("<i>", scope_html({"name": "a", "role": "employee", "company_id": "<i>"}))


if __name__ == "__main__":
    unittest.main()
