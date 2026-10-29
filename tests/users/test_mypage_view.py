"""M-02 마이페이지 비밀번호 변경 폼 테스트.

Streamlit AppTest로 실제 렌더링·버튼 클릭을 재현하고, 서비스(user_service)는 가짜로 바꿔 DB 없이 돈다.
무엇을 확인하나 — 실패 원인마다 '다른 안내'가 뜨는지, 그리고 성공하면 폼이 닫히고 안내가 한 번 뜨는지.

실행: python -m unittest tests.users.test_mypage_view
"""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

UID = "app.users.views.mypage.get_current_user_id"
INFO = "app.users.views.mypage.get_user_info"
HISTORY = "app.users.views.mypage.get_access_request_history"
CHANGE = "app.users.views.mypage.change_password"

PROFILE = {
    "user_id": 1,
    "employee_no": "MVX-0001",
    "name": "홍길동",
    "email": None,
    "role": "employee",
    "company_id": "MVX",
    "company_name": "현대무벡스",
}


def _mypage_app():
    from app.users.views.mypage import render_mypage

    render_mypage()


class ChangePasswordFormTest(unittest.TestCase):
    """비밀번호 변경 폼. validate_password는 진짜(순수 함수)를 쓰고, change_password만 가짜로 바꾼다."""

    def _open_form(self):
        # 조회 함수는 DB를 타므로 전부 가짜로 바꾼다 (프로필·요청 목록·현재 사용자).
        for target, value in ((UID, 1), (INFO, PROFILE), (HISTORY, [])):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        at = AppTest.from_function(_mypage_app).run(timeout=30)
        # '비밀번호 바꾸기'를 눌러 폼을 연다.
        [b for b in at.button if b.label == "비밀번호 바꾸기"][0].click().run(timeout=30)
        return at

    def _submit(self, at, current, new, confirm):
        # 폼 입력칸은 키가 없어 그린 순서(현재→새→새 확인)대로 접근한다.
        at.text_input[0].input(current)
        at.text_input[1].input(new)
        at.text_input[2].input(confirm)
        [b for b in at.button if b.label == "변경"][0].click().run(timeout=30)
        return at

    def test_confirm_mismatch_shows_distinct_message_and_skips_service(self):
        """새 비밀번호와 확인이 다르면 그 안내만 뜨고 서비스는 호출되지 않는다."""
        at = self._open_form()
        with patch(CHANGE) as change:
            self._submit(at, "oldpass12", "newpass12", "different12")

        self.assertEqual([e.value for e in at.error], ["새 비밀번호와 확인이 일치하지 않습니다."])
        change.assert_not_called()

    def test_rule_violation_shows_distinct_message_and_skips_service(self):
        """새 비밀번호가 규칙(8~20자, 영문·숫자)에 안 맞으면 그 안내만 뜨고 서비스는 호출되지 않는다."""
        at = self._open_form()
        with patch(CHANGE) as change:
            # 'short'는 8자 미만이라 규칙 위반. 서비스에 가기 전에 걸러야 한다.
            self._submit(at, "oldpass12", "short", "short")

        self.assertEqual(len(at.error), 1)
        self.assertIn("규칙", at.error[0].value)
        self.assertNotIn("현재 비밀번호", at.error[0].value)  # 현재 비밀번호 불일치와 구분된다
        change.assert_not_called()

    def test_wrong_current_password_shows_distinct_message(self):
        """규칙은 통과했는데 서비스가 False(현재 비밀번호 불일치)면 그 안내가 뜬다."""
        at = self._open_form()
        with patch(CHANGE, return_value=False) as change:
            self._submit(at, "wrongpass1", "newpass12", "newpass12")

        self.assertEqual([e.value for e in at.error], ["현재 비밀번호가 올바르지 않습니다."])
        change.assert_called_once_with(1, "wrongpass1", "newpass12")

    def test_success_closes_form_and_announces_once(self):
        """성공하면 폼이 닫히고(입력칸 사라짐) 성공 안내가 한 번 뜬다."""
        at = self._open_form()
        with patch(CHANGE, return_value=True):
            self._submit(at, "oldpass12", "newpass12", "newpass12")

        self.assertEqual([s.value for s in at.success], ["비밀번호를 변경했습니다."])
        self.assertEqual(len(at.error), 0)
        # 폼이 닫혀 입력칸(현재/새/새 확인)이 더 이상 그려지지 않는다.
        self.assertEqual(len(at.text_input), 0)
        self.assertNotIn("change_password_open", at.session_state)


class AccessRequestListTest(unittest.TestCase):
    """열람 권한 요청 목록. 목록은 M-04 history_service.get_access_request_history() 반환 모양을 그대로 쓴다."""

    REQUEST = {
        "request_id": 1, "doc_id": "d1", "title": "엘리베이터 단가표", "owner_company_code": "ELV",
        "reason": "견적 비교", "status": "rejected", "status_label": "반려", "review_comment": "기밀 문서",
        "created_at": "2026-10-27 09:00", "reviewed_at": "2026-10-27 15:00",
    }

    def test_rejected_request_shows_title_time_and_reject_reason(self):
        for target, value in ((UID, 1), (INFO, PROFILE), (HISTORY, [self.REQUEST])):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        at = AppTest.from_function(_mypage_app).run(timeout=30)

        self.assertIsNone(at.exception or None)
        page = " ".join(str(element.proto) for element in at.get("html"))
        for text in ("엘리베이터 단가표", "2026-10-27 09:00", "반려 사유: 기밀 문서"):
            self.assertIn(text, page)


if __name__ == "__main__":
    unittest.main()
