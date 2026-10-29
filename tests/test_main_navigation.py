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
             patch("app.admin.views.access_requests.render_admin_permissions") as render_permissions, \
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
                requests = [item for group in menus.values() for item in group
                            if getattr(item, "url_path", None) == "admin-access-requests"]
                self.assertEqual(len(requests), 0 if role == "employee" else 1)
                if requests:
                    requests[0].render()
                    render_permissions.assert_called_with(user)



    def test_audit_log_and_company_menus_are_wired_by_role(self):
        """감사 로그는 두 관리자에게, 계열사는 최종 어드민에게만 노출하고 세션 사용자를 전달한다."""
        def page(render, **options):
            """실행 없이 메뉴 구성을 검사한다."""
            return SimpleNamespace(render=render, **options)

        expected = {  # url_path -> 메뉴를 보는 역할
            "admin-audit-logs": ("company_admin", "super_admin"),
            "admin-companies": ("super_admin",),
        }
        with patch("streamlit.Page", side_effect=page),              patch("streamlit.navigation"),              patch("app.auth.session.is_authenticated", return_value=False),              patch("app.admin.views.audit_logs.render_admin_audit_logs") as audit_render,              patch("app.admin.views.companies.render_admin_companies") as company_render:
            namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"))
            for role in ("employee", "company_admin", "super_admin"):
                user = {"id": 1, "role": role, "company_id": "MVX"}
                menus = namespace["build_pages"](user)
                for url_path, roles in expected.items():
                    items = [item for group in menus.values() for item in group
                             if getattr(item, "url_path", None) == url_path]
                    self.assertEqual(len(items), 1 if role in roles else 0, (role, url_path))
                    if items:
                        # "준비 중" 자리가 아니라 실제 화면 함수가 연결돼야 한다.
                        render = audit_render if url_path == "admin-audit-logs" else company_render
                        items[0].render()
                        render.assert_called_with(user)
