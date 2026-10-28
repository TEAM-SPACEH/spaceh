import unittest

from app.common.ui import (
    citation_html,
    company_tag_html,
    file_type_html,
    highlight_html,
    security_badge_html,
    stat_card_html,
    status_tag_html,
    text_html,
)


class CommonUiHtmlTest(unittest.TestCase):
    def test_security_badge_labels(self):
        self.assertIn("공개", security_badge_html("public"))
        self.assertIn("sh-int", security_badge_html("internal"))
        self.assertIn("기밀", security_badge_html("confidential"))

    def test_unknown_level_is_shown_as_is(self):
        self.assertIn("unknown", security_badge_html("unknown"))

    def test_text_is_escaped(self):
        self.assertNotIn("<script>", highlight_html("<script>x</script>"))
        self.assertNotIn("<b>", company_tag_html("<b>MVX</b>"))

    def test_markdown_in_title_stays_plain_text(self):
        """제목 속 Markdown 링크·이미지는 글자 그대로 남고 태그가 되지 않는다 (st.html은 Markdown을 해석하지 않음)."""
        out = text_html("[확인](https://example.com) ![x](https://example.com/a.png) <img src=x>", bold=True)
        self.assertIn("[확인](https://example.com)", out)
        self.assertNotIn("<a", out)
        self.assertNotIn("<img", out)

    def test_citation_number_only(self):
        self.assertIn(">3<", citation_html(3))
        with self.assertRaises(ValueError):
            citation_html("1<b>")

    def test_status_label_depends_on_kind(self):
        """같은 pending이라도 색인은 '대기', 열람 요청은 '검토 중'이다."""
        self.assertIn("대기", status_tag_html("index", "pending"))
        self.assertIn("검토 중", status_tag_html("request", "pending"))
        self.assertIn("sh-st-ok", status_tag_html("index", "done"))
        self.assertIn("sh-st-bad", status_tag_html("request", "rejected"))
        self.assertIn("수집 중", status_tag_html("dart", "running"))

    def test_unknown_status_is_gray_and_escaped(self):
        out = status_tag_html("index", "<b>weird</b>")
        self.assertIn("sh-muted", out)
        self.assertNotIn("<b>", out)
        # 다른 종류의 값(approved는 색인 상태가 아님)도 모르는 값으로 본다.
        self.assertIn("sh-muted", status_tag_html("index", "approved"))

    def test_file_type_labels(self):
        self.assertIn(">PDF<", file_type_html("pdf"))
        self.assertIn(">PPT<", file_type_html("pptx"))
        self.assertIn(">DART<", file_type_html("dart_xml"))
        self.assertNotIn("<i>", file_type_html("<i>x"))

    def test_stat_card(self):
        out = stat_card_html("전체 문서", 1284, "이번 주 6건 추가", tone="bad")
        self.assertIn("1,284", out)
        self.assertIn("sh-dot-bad", out)
        self.assertNotIn("<script>", stat_card_html("<script>", "x"))
        self.assertNotIn("sh-dot", stat_card_html("색인", 1, tone="unknown"))


if __name__ == "__main__":
    unittest.main()
