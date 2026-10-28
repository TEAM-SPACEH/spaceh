"""A-01 Chrome 좌표 검증이 배치 오류를 실제 실패로 처리하는지 확인한다."""

from copy import deepcopy
import unittest

from scripts.check_upload_layout import validate_report


class UploadLayoutCheckTest(unittest.TestCase):
    def test_rejects_alignment_clipping_missing_font_and_missing_cases(self):
        """A-01 문구 처짐·스피너 처짐·잘림·폰트 및 측정 누락을 거부한다."""
        report = {"fontLoaded": True, "controlsOk": True, "controlContrast": [4.5] * 5, "rows": [
            {"fits": True, "textDelta": 0, "spinnerDelta": 0, "contrast": 4.5} for _ in range(16)
        ]}
        validate_report(report)
        for key, value in (("textDelta", 4), ("spinnerDelta", 4), ("fits", False), ("contrast", 4.49)):
            with self.subTest(key=key):
                bad = deepcopy(report)
                bad["rows"][0][key] = value
                with self.assertRaises(ValueError):
                    validate_report(bad)
        for bad in ({**report, "controlsOk": False},
                    {**report, "controlContrast": [4.49] * 5},
                    {**report, "controlContrast": []},
                    {"fontLoaded": False, "rows": report["rows"]},
                    {"fontLoaded": True, "rows": []}):
            with self.assertRaises(ValueError):
                validate_report(bad)
