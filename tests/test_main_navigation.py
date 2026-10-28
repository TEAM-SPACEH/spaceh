"""A-01 메인 메뉴 연결과 로그인 경계 검증."""

from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class MainNavigationTest(unittest.TestCase):
    def test_login_page_renders_without_session(self):
        """로그인 전에는 기존 로그인 폼만 표시한다."""
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py")).run()
        self.assertFalse(app.exception)
        self.assertIn("로그인", [button.label for button in app.button])
        self.assertNotIn("문서 올리기", [button.label for button in app.button])

    def test_document_menu_is_admin_only_and_passes_session_user(self):
        """두 관리자 역할에만 문서 메뉴를 노출하고 해당 사용자를 전달한다."""
        def page(render, **options):
            """실행 없이 메뉴 구성을 검사한다."""
            return SimpleNamespace(render=render, **options)

        with patch("streamlit.Page", side_effect=page), \
             patch("streamlit.navigation"), \
             patch("app.auth.session.is_authenticated", return_value=False), \
             patch("app.admin.views.documents.render_admin_documents") as render:
            namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"))
            for role in ("employee", "company_admin", "super_admin"):
                user = {"id": 1, "role": role, "company_id": "MVX"}
                menus = namespace["build_pages"](user)
                documents = [item for group in menus.values() for item in group
                             if getattr(item, "url_path", None) == "admin-documents"]
                self.assertEqual(len(documents), 0 if role == "employee" else 1)
                if documents:
                    documents[0].render()
                    render.assert_called_with(user)
