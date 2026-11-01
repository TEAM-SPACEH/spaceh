import re
import unittest
from pathlib import Path

from app.common.ui import DOC_TYPE_LABELS
from core.constants import DOC_TYPES

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


class DocTypeConstantsTest(unittest.TestCase):
    def test_doc_types_match_schema_check(self):
        """문서 유형 상수와 DB CHECK 제약(ck_documents_doc_type)의 값이 같아야 한다."""
        match = re.search(r"ck_documents_doc_type CHECK \(.*?IN \(([^)]*)\)\)", SCHEMA.read_text(encoding="utf-8"))
        self.assertIsNotNone(match)
        self.assertEqual(tuple(re.findall(r"'([^']+)'", match.group(1))), DOC_TYPES)

    def test_every_doc_type_has_label(self):
        """화면 이름은 모든 유형에 하나씩, 상수와 같은 순서로 있다."""
        self.assertEqual(tuple(DOC_TYPE_LABELS), DOC_TYPES)


if __name__ == "__main__":
    unittest.main()
