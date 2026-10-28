"""A-01 상태 행의 실제 Chrome 정렬 검사: python -m scripts.check_upload_layout."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from app.common.ui import _CSS, upload_status_html
from core.config import ROOT_DIR


_CONTROLS = """
<div class="stApp">
  <div class="stButton"><button kind="primary" data-color="rgb(255, 255, 255)"><div data-testid="stMarkdownContainer">업로드</div></button></div>
  <div class="stButton"><button kind="secondary" data-color="rgb(0, 153, 68)"><div data-testid="stMarkdownContainer">닫기</div></button></div>
  <div class="stButton"><button kind="tertiary" data-color="rgb(0, 64, 152)"><div data-testid="stMarkdownContainer">전체 지우기</div></button></div>
  <div data-testid="stMarkdownContainer" id="body-text">본문</div>
  <div class="st-key-upload-picker"><div data-testid="stFileUploaderDropzone">
    <span><button id="choose"><span>Upload</span></button></span>
  </div></div>
  <div class="st-key-upload-picker"><div data-testid="stFileUploaderDropzone">
    <div><button class="keep-label"><span>Cancel upload</span></button></div>
    <div><button class="keep-label"><span>Remove file</span></button></div>
  </div></div>
</div>
"""


_MEASURE = """
<script>
document.fonts.ready.then(() => {
  const rows = [...document.querySelectorAll('section')].map(section => {
    const box = section.querySelector('.sh-upload-status');
    const text = box.querySelector('span:last-child');
    const spinner = box.querySelector('.sh-upload-spinner');
    const a = box.getBoundingClientRect(), b = text.getBoundingClientRect();
    const c = spinner && spinner.getBoundingClientRect();
    return {
      width: +section.dataset.width, zoom: +section.dataset.zoom,
      status: section.dataset.status,
      textDelta: Math.abs((a.top + a.bottom - b.top - b.bottom) / 2),
      spinnerDelta: c ? Math.abs((a.top + a.bottom - c.top - c.bottom) / 2) : 0,
      fits: a.height > 0 && b.height > 0 && b.left >= a.left - .5 &&
        b.right <= a.right + .5 && b.top >= a.top - .5 && b.bottom <= a.bottom + .5
    };
  });
  const report = document.createElement('pre');
  report.id = 'audit-report';
  const controlsOk = [...document.querySelectorAll('button[data-color]')].every(button =>
    getComputedStyle(button.querySelector('[data-testid="stMarkdownContainer"]')).color === button.dataset.color
  ) && getComputedStyle(document.querySelector('#body-text')).color === 'rgb(17, 17, 17)' &&
    getComputedStyle(document.querySelector('#choose'), '::after').content.includes('내 컴퓨터에서 파일 선택') &&
    [...document.querySelectorAll('.keep-label')].every(button =>
      ['none', 'normal'].includes(getComputedStyle(button, '::after').content) &&
      getComputedStyle(button.firstElementChild).display !== 'none');
  report.textContent = JSON.stringify({
    fontLoaded: [...document.fonts].some(f => f.family === 'NeoHyundai' && f.status === 'loaded') &&
      document.fonts.check('13px NeoHyundai'), rows, controlsOk
  });
  document.body.append(report);
});
</script>
"""


def validate_report(report: dict) -> None:
    """A-01 폰트 누락·검사 누락·중앙 오차·문구 잘림을 실패로 처리한다."""
    if not report.get("fontLoaded") or len(report.get("rows", [])) != 16:
        raise ValueError("네오현대 폰트 로딩 또는 16개 검사 조건을 확인하지 못했습니다.")
    if not report.get("controlsOk"):
        raise ValueError("버튼 글자 색상 또는 파일 선택·취소·제거 라벨 검사에 실패했습니다.")
    for row in report["rows"]:
        if not row["fits"] or row["textDelta"] > 0.5 or row["spinnerDelta"] > 0.5:
            raise ValueError(f"정렬 검사 실패: {row}")


def main() -> None:
    """A-01 로컬 폰트와 실제 상태 HTML·CSS를 Chrome에서 렌더링해 검사한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chrome")
                        or str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                               / "Google/Chrome/Application/chrome.exe"))
    args = parser.parse_args()
    if not Path(args.chrome).is_file():
        parser.error("Chrome 실행 파일을 찾을 수 없습니다. --chrome 경로를 지정하세요.")
    font_dir = ROOT_DIR / "static/fonts"
    for name in ("NeoHyundai-R.ttf", "NeoHyundai-B.ttf"):
        if not (font_dir / name).is_file():
            parser.error(f"폰트 파일이 없습니다: {name}")
    css = _CSS.replace('url("app/static/fonts/', f'url("{font_dir.as_uri()}/')
    rows = []
    messages = {"busy": "문서를 저장하고 색인합니다.", "done": "색인 완료 · 청크 366개",
                "duplicate": "이미 등록된 파일입니다. 기존 문서를 확인해 주세요.",
                "failed": "색인 실패: 문서 상태를 확인한 뒤 다시 처리해 주세요."}
    for width in (280, 520):
        for zoom in (1, 1.25):
            for status, message in messages.items():
                rows.append(f'<section data-width="{width}" data-zoom="{zoom}" '
                            f'data-status="{status}" style="width:{width}px;zoom:{zoom};margin:12px">'
                            + upload_status_html(message, status) + '</section>')
    with TemporaryDirectory(prefix="spaceh-layout-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        page = root / "check.html"
        page.write_text('<!doctype html><meta charset="utf-8">' + css + ''.join(rows)
                        + _CONTROLS + _MEASURE, encoding="utf-8")
        process = subprocess.run(
            [args.chrome, "--headless", "--disable-gpu", "--no-first-run", "--dump-dom",
             "--virtual-time-budget=3000", f"--user-data-dir={root / 'profile'}", page.as_uri()],
            capture_output=True, encoding="utf-8", timeout=30, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        match = re.search(r'<pre id="audit-report">(.*?)</pre>', process.stdout, re.S)
        if match is None:
            raise ValueError("Chrome 측정 결과가 없습니다. 브라우저 실행 환경을 확인하세요.")
        validate_report(json.loads(html.unescape(match[1])))
    print("PASS: 상태 행 16조건 정렬·잘림 + 버튼 3종·본문 색상 + 파일 선택·취소·제거 라벨")


if __name__ == "__main__":
    main()
