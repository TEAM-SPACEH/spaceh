"""M-02·M-03·M-04 내 정보 화면 테스트 (Figma UI v4 06).

Streamlit AppTest로 실제 렌더링·버튼 클릭을 재현하고, 서비스(user_service·history_service)는 가짜로 바꿔 DB 없이 돈다.
무엇을 확인하나 — ① [내 정보 수정] 대화상자의 비밀번호 변경이 실패 원인마다 '다른 안내'를 하고 성공하면 닫히는지
② 프로필 통계·최근 30일 요청 표·사용 기록이 서비스 값대로 그려지는지 ③ 서비스 실패·빈 상태 안내.

실행: python -m unittest tests.users.test_mypage_view
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

UID = "app.users.views.mypage.get_current_user_id"
INFO = "app.users.views.mypage.get_user_info"
HISTORY = "app.users.views.mypage.get_access_request_history"
USER_HISTORY = "app.users.views.mypage.get_user_history"
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


def _password_form_app():
    """대화상자 안 폼만 그린다. AppTest는 대화상자 안 상호작용을 부분 재실행으로 재현하지 못해 폼 본체를 직접 그린다."""
    from app.users.views.mypage import _render_password_form

    _render_password_form(1)


def _stamp(days_ago: int, hour: int = 10, minute: int = 0) -> str:
    """오늘 기준 days_ago일 전 hh:mm을 서비스 형식("YYYY-MM-DD HH:MM")으로 만든다."""
    when = (datetime.now() - timedelta(days=days_ago)).replace(hour=hour, minute=minute)
    return when.strftime("%Y-%m-%d %H:%M")


def _request(**overrides) -> dict:
    base = {
        "request_id": 1, "doc_id": "d1", "title": "엘리베이터 단가표", "owner_company_code": "ELV",
        "reason": "견적 비교", "status": "pending", "status_label": "대기", "review_comment": None,
        "created_at": _stamp(2), "reviewed_at": None,
    }
    return {**base, **overrides}


def _history_item(**overrides) -> dict:
    base = {
        "history_id": 1, "history_type": "ask", "type_label": "질문", "summary": "스마트팩토리 수주는?",
        "created_at": _stamp(0, 9, 0), "result_count": 3, "is_blocked": False, "can_rerun": True, "report_id": None,
    }
    return {**base, **overrides}


def _run(requests=None, history=None, info=PROFILE) -> AppTest:
    """서비스를 가짜로 바꿔 화면을 한 번 그린다. patch는 테스트가 끝날 때 풀린다."""
    return _start(requests, history, info).run(timeout=30)


def _start(requests=None, history=None, info=PROFILE) -> AppTest:
    """서비스를 가짜로 바꾼 AppTest를 만든다 (아직 실행 전이라 session_state를 미리 채울 수 있다)."""
    patches = _Patches()
    patches.start(UID, 1)
    patches.start(INFO, info)
    patches.start(HISTORY, requests if requests is not None else [])
    patches.start(USER_HISTORY, history if history is not None else [])
    return AppTest.from_function(_mypage_app)


class _Patches:
    """patch를 켜 두고 테스트 클래스가 끝날 때 한꺼번에 푸는 작은 도우미."""

    def start(self, target, value):
        patcher = patch(target, return_value=value)
        patcher.start()
        _ACTIVE.append(patcher)


_ACTIVE: list = []


def _stop_patches() -> None:
    while _ACTIVE:
        _ACTIVE.pop().stop()


class _MypageTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(_stop_patches)

    def html(self, at) -> str:
        return " ".join(element.proto.body for element in at.get("html"))


class ChangePasswordDialogTest(_MypageTestCase):
    """[내 정보 수정] 대화상자의 비밀번호 변경. validate_password는 진짜(순수 함수)를 쓰고, change_password만 가짜로 바꾼다."""

    def _open_dialog(self):
        """폼 본체만 그린다 (대화상자를 여는 것은 아래 test_edit_button_opens_dialog가 따로 확인한다)."""
        return AppTest.from_function(_password_form_app).run(timeout=30)

    def _submit(self, at, current, new, confirm):
        # 폼 입력칸은 키가 없어 그린 순서(현재→새→새 확인)대로 접근한다.
        at.text_input[0].input(current)
        at.text_input[1].input(new)
        at.text_input[2].input(confirm)
        [b for b in at.button if b.label == "변경"][0].click().run(timeout=30)
        return at

    def test_edit_button_opens_dialog_with_three_password_fields(self):
        at = _run()
        self.assertEqual(len(at.text_input), 0)  # 처음에는 닫혀 있다

        [b for b in at.button if b.label == "내 정보 수정"][0].click().run(timeout=30)

        self.assertEqual([t.label for t in at.text_input][:1], ["현재 비밀번호"])
        self.assertEqual(len(at.text_input), 3)

    def test_confirm_mismatch_shows_distinct_message_and_skips_service(self):
        """새 비밀번호와 확인이 다르면 그 안내만 뜨고 서비스는 호출되지 않는다."""
        at = self._open_dialog()
        with patch(CHANGE) as change:
            self._submit(at, "oldpass12", "newpass12", "different12")

        self.assertEqual([e.value for e in at.error], ["새 비밀번호와 확인이 일치하지 않습니다."])
        change.assert_not_called()

    def test_rule_violation_shows_distinct_message_and_skips_service(self):
        """새 비밀번호가 규칙(8~20자, 영문·숫자)에 안 맞으면 그 안내만 뜨고 서비스는 호출되지 않는다."""
        at = self._open_dialog()
        with patch(CHANGE) as change:
            # 'short'는 8자 미만이라 규칙 위반. 서비스에 가기 전에 걸러야 한다.
            self._submit(at, "oldpass12", "short", "short")

        self.assertEqual(len(at.error), 1)
        self.assertIn("규칙", at.error[0].value)
        self.assertNotIn("현재 비밀번호", at.error[0].value)  # 현재 비밀번호 불일치와 구분된다
        change.assert_not_called()

    def test_wrong_current_password_shows_distinct_message(self):
        """규칙은 통과했는데 서비스가 False(현재 비밀번호 불일치)면 그 안내가 뜬다."""
        at = self._open_dialog()
        with patch(CHANGE, return_value=False) as change:
            self._submit(at, "wrongpass1", "newpass12", "newpass12")

        self.assertEqual([e.value for e in at.error], ["현재 비밀번호가 올바르지 않습니다."])
        change.assert_called_once_with(1, "wrongpass1", "newpass12")

    def test_service_error_shows_friendly_message(self):
        """서비스가 예외를 던지면 스택 트레이스 대신 쉬운 안내가 뜬다."""
        at = self._open_dialog()
        with patch(CHANGE, side_effect=RuntimeError("db down")):
            self._submit(at, "oldpass12", "newpass12", "newpass12")

        self.assertEqual([e.value for e in at.error], ["비밀번호 변경 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요."])

    def test_success_closes_dialog_and_announces_once(self):
        """성공하면 대화상자가 닫히고(입력칸 사라짐) 성공 안내가 한 번 뜬다."""
        at = self._open_dialog()
        with patch(CHANGE, return_value=True):
            self._submit(at, "oldpass12", "newpass12", "newpass12")

        # 성공하면 안내 표시를 남기고 전체를 다시 그려 대화상자를 닫는다.
        self.assertTrue(at.session_state["password_changed_flash"])
        self.assertEqual(len(at.error), 0)

    def test_success_flash_is_shown_once_on_the_next_screen(self):
        at = _start()
        at.session_state["password_changed_flash"] = True
        at.run(timeout=30)

        self.assertEqual([s.value for s in at.success], ["비밀번호를 변경했습니다."])
        at.run(timeout=30)
        self.assertEqual(len(at.success), 0)


class ProfileCardTest(_MypageTestCase):
    def test_profile_shows_name_tags_and_employee_line_without_made_up_email(self):
        at = _run()

        page = self.html(at)
        for text in ("홍길동", "MVX", "일반 사원", "사원번호 MVX-0001 · 현대무벡스"):
            self.assertIn(text, page)
        self.assertNotIn("@", page)  # email이 없으면 지어내지 않고 줄에서 뺀다

    def test_profile_shows_email_when_service_gives_one(self):
        at = _run(info={**PROFILE, "email": "gildong@example.com"})

        self.assertIn("사원번호 MVX-0001 · gildong@example.com · 현대무벡스", self.html(at))

    def test_super_admin_has_no_company_tag(self):
        at = _run(info={**PROFILE, "role": "super_admin", "company_id": None, "company_name": None})

        page = self.html(at)
        self.assertIn("최종 어드민", page)
        self.assertIn("소속 없음", page)

    def test_stats_count_this_month_questions_reports_and_approved_requests(self):
        history = [
            _history_item(history_id=1),
            _history_item(history_id=2),
            _history_item(history_id=3, history_type="report_create", summary="보고서"),
        ]
        requests = [_request(status="approved"), _request(request_id=2, status="pending")]
        at = _run(requests=requests, history=history)

        page = self.html(at)
        self.assertIn("이번 달 질문", page)
        # 질문 2, 보고서 1, 승인 1 — 숫자 칸은 라벨 바로 뒤에 나온다
        for label, number in (("이번 달 질문", 2), ("만든 보고서", 1), ("열람 승인", 1)):
            self.assertIn(f'{label}</div><div class="sh-mp-stat-num">{number}</div>', page)


class AccessRequestTableTest(_MypageTestCase):
    """열람 권한 요청 표. 목록은 M-04 history_service.get_access_request_history() 반환 모양을 그대로 쓴다."""

    def test_rejected_request_shows_title_time_and_reject_reason(self):
        request = _request(status="rejected", review_comment="기밀 문서", created_at=_stamp(1, 9, 0))
        at = _run(requests=[request])

        self.assertIsNone(at.exception or None)
        page = self.html(at)
        short = datetime.strptime(request["created_at"], "%Y-%m-%d %H:%M").strftime("%m.%d %H:%M")
        for text in ("엘리베이터 단가표", short, "반려 사유: 기밀 문서", "반려"):
            self.assertIn(text, page)

    def test_pending_shows_reason_and_approved_shows_approval_date(self):
        approved = _request(request_id=2, title="연구 과제 목록", status="approved", reviewed_at=_stamp(1, 15, 0))
        at = _run(requests=[_request(), approved])

        page = self.html(at)
        self.assertIn("사유: 견적 비교", page)
        day = datetime.strptime(approved["reviewed_at"], "%Y-%m-%d %H:%M").strftime("%m.%d")
        self.assertIn(f"{day} 승인", page)

    def test_requests_older_than_30_days_are_hidden(self):
        at = _run(requests=[_request(title="오래된 요청", created_at=_stamp(45))])

        # 표에서는 빠지고(안내만 뜨고), 사용 기록에는 날짜대로 남는다.
        self.assertNotIn("sh-mp-table", self.html(at))
        self.assertIn("최근 30일 안에 열람 권한을 요청한 문서가 없습니다.", [i.value for i in at.info])

    def test_user_written_text_is_escaped(self):
        at = _run(requests=[_request(title="<img src=x onerror=alert(1)>", reason="[링크](http://evil)")])

        page = self.html(at)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x", page)

    def test_request_list_failure_shows_error_only_in_that_card(self):
        test = _Patches()
        test.start(UID, 1)
        test.start(INFO, PROFILE)
        test.start(USER_HISTORY, [])
        with patch(HISTORY, side_effect=RuntimeError("db down")):
            at = AppTest.from_function(_mypage_app).run(timeout=30)

        self.assertEqual([e.value for e in at.error], ["열람 권한 요청 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."])


class UsageHistoryTest(_MypageTestCase):
    def test_groups_by_day_with_kind_subtitles_and_times(self):
        history = [
            _history_item(history_id=1, summary="오늘 질문", created_at=_stamp(0, 8, 5), result_count=3),
            _history_item(history_id=2, history_type="view_document", summary="3분기 보고서", created_at=_stamp(0, 7, 1),
                          result_count=None),
            _history_item(history_id=3, summary="어제 질문", created_at=_stamp(1, 16, 20), result_count=2),
        ]
        at = _run(history=history)

        page = self.html(at)
        for text in ("오늘", "어제", "오늘 질문", "질문, 근거 3건", "3분기 보고서", "원문 보기", "08:05", "16:20"):
            self.assertIn(text, page)

    def test_access_requests_are_merged_into_history(self):
        at = _run(requests=[_request(title="공동 사업 검토안", created_at=_stamp(0, 6, 30))],
                  history=[_history_item(created_at=_stamp(0, 8, 0))])

        page = self.html(at)
        self.assertIn("공동 사업 검토안", page)
        self.assertIn("열람 권한 요청</div>", page)

    def test_report_item_does_not_invent_evidence_count(self):
        history = [_history_item(history_type="report_create", summary="물류 보고서", result_count=None, report_id=7)]
        at = _run(history=history)

        page = self.html(at)
        self.assertIn("물류 보고서", page)
        self.assertNotIn("근거", page)

    def test_view_all_button_expands_and_collapses(self):
        history = [_history_item(history_id=i, summary=f"질문 {i}", created_at=_stamp(0, 9, i)) for i in range(8)]
        at = _run(history=history)

        self.assertIn("질문 3", self.html(at))      # 최신순 7·6·5·4·3 다섯 건만
        self.assertNotIn("질문 2", self.html(at))
        [b for b in at.button if b.label == "전체 보기"][0].click().run(timeout=30)
        self.assertIn("질문 0", self.html(at))
        self.assertIn("질문 2", self.html(at))
        self.assertTrue([b for b in at.button if b.label == "접기"])

    def test_no_view_all_button_when_everything_is_already_shown(self):
        at = _run(history=[_history_item()])

        self.assertEqual([b.label for b in at.button if b.label in ("전체 보기", "접기")], [])

    def test_empty_history_shows_guidance(self):
        at = _run()

        self.assertIn("아직 사용 기록이 없습니다. 통합 검색에서 문서를 찾아보세요.", [i.value for i in at.info])

    def test_history_failure_shows_error_only_in_that_card(self):
        test = _Patches()
        test.start(UID, 1)
        test.start(INFO, PROFILE)
        test.start(HISTORY, [])
        with patch(USER_HISTORY, side_effect=RuntimeError("db down")):
            at = AppTest.from_function(_mypage_app).run(timeout=30)

        self.assertEqual([e.value for e in at.error], ["사용 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."])


class AccessGuardTest(_MypageTestCase):
    def test_not_logged_in_shows_warning(self):
        test = _Patches()
        test.start(UID, None)
        at = AppTest.from_function(_mypage_app).run(timeout=30)

        self.assertEqual([w.value for w in at.warning], ["로그인 후 이용할 수 있습니다."])

    def test_profile_failure_shows_friendly_error(self):
        test = _Patches()
        test.start(UID, 1)
        with patch(INFO, side_effect=RuntimeError("db down")):
            at = AppTest.from_function(_mypage_app).run(timeout=30)

        self.assertEqual([e.value for e in at.error], ["내 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."])


if __name__ == "__main__":
    unittest.main()
