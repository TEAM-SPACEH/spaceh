import unittest

from app.common.ui import citation_html, company_tag_html, highlight_html, security_badge_html, text_html


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


if __name__ == "__main__":
    unittest.main()
