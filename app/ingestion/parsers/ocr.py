"""I-01 공통 이미지 OCR. CPU 작업을 별도 프로세스에서 실행한다."""

import atexit
import base64
import io
import json
import logging
import queue
import subprocess
import sys
import threading
import unicodedata
from contextvars import ContextVar
from functools import wraps
from time import monotonic

from PIL import Image

from core import config

_lock = threading.Lock()
_process = None
_connection = None
logger = logging.getLogger(__name__)
_budget = ContextVar("ocr_budget", default=None)


class OcrModelError(RuntimeError):
    """I-01 패키지·모델 준비 또는 워커 통신 오류."""


def ocr_limit_reached() -> bool:
    """I-01 현재 문서의 남은 OCR 처리 여유를 확인한다."""
    state = _budget.get()
    return bool(state and (state["unavailable"] or state["count"] >= config.OCR_MAX_IMAGES
                           or state["seconds"] >= config.OCR_DOCUMENT_SECONDS))


def ocr_document(parser):
    """I-01 문서마다 OCR 호출 수·누적 시간 제한을 새로 적용한다."""
    @wraps(parser)
    def parse(*args, **kwargs):
        token = _budget.set({"count": 0, "seconds": 0.0, "unavailable": False})
        try:
            return parser(*args, **kwargs)
        finally:
            _budget.reset(token)
    return parse


def _worker():
    """모델은 프로세스당 한 번만 읽고 원문·오류 원문은 출력하지 않는다."""
    try:
        reader = None
        for line in sys.stdin.buffer:
            data = base64.b64decode(line)
            if reader is None:
                import easyocr
                reader = easyocr.Reader(
                    ["ko", "en"], gpu=False, model_storage_directory=sys.argv[1],
                    download_enabled=False, verbose=False,
                )
            lines = reader.readtext(data, detail=0, paragraph=False, workers=0)
            print(json.dumps((True, lines)), flush=True)
    except Exception as error:
        try:
            print(json.dumps((False, ("model" if reader is None else "image", type(error).__name__))), flush=True)
        except (BrokenPipeError, EOFError, OSError):
            pass  # 부모가 시간 초과로 닫았으면 오류를 다시 보내지 않는다.


class _WorkerPipe:
    """표준 출력 읽기를 분리해 Windows에서도 응답 대기 시간을 제한한다."""
    def __init__(self, process):
        self.process = process
        self.responses = queue.Queue()
        self.response = None

    def send_bytes(self, data):
        self.process.stdin.write(base64.b64encode(data) + b"\n")
        self.process.stdin.flush()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        self.responses.put(self.process.stdout.readline())

    def poll(self, timeout):
        try:
            self.response = self.responses.get(timeout=timeout)
            return True
        except queue.Empty:
            return False

    def recv(self):
        if not self.response:
            raise EOFError()
        return json.loads(self.response)

    def close(self):
        try:
            self.process.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # 종료된 워커의 입력 버퍼는 다시 보낼 수 없다.
        self.process.stdout.close()


def _close_worker():
    """OCR 프로세스와 입출력을 정리하고 다음 호출에서 다시 시작하게 한다."""
    global _process, _connection
    if _process is not None:
        if _process.poll() is None:
            _process.terminate()
        _process.wait(timeout=5)
    if _connection is not None:
        _connection.close()
    _process = _connection = None


atexit.register(_close_worker)


def _extract_image_text(data: bytes, existing_text: str = "", timeout: float | None = None) -> str:
    """I-01 이미지 글자를 읽고 기존 텍스트와 같은 OCR 줄은 제외한다."""
    global _process, _connection
    # 디코딩 크기를 검사해 비정상 이미지로 인한 메모리 사용을 제한한다.
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > config.OCR_MAX_PIXELS:
            raise ValueError("OCR 이미지 크기 한도를 초과했습니다.")
    with _lock:
        if _process is None or _process.poll() is not None:
            _close_worker()
            _process = subprocess.Popen(
                [sys.executable, "-m", "app.ingestion.parsers.ocr", str(config.OCR_MODEL_DIR)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=config.ROOT_DIR,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            _connection = _WorkerPipe(_process)
        try:
            _connection.send_bytes(data)
            if not _connection.poll(timeout if timeout is not None else config.OCR_TIMEOUT_SECONDS):
                raise TimeoutError("OCR 처리 시간 한도를 초과했습니다.")
            success, lines = _connection.recv()
            if not success:
                stage = lines[0] if lines else "model"
                if stage == "model":
                    raise OcrModelError("OCR 모델 준비와 패키지 설치를 확인하세요.")
                raise RuntimeError("OCR 이미지 형식 또는 손상을 확인하세요.")
        except TimeoutError:
            _close_worker()
            raise
        except (BrokenPipeError, EOFError, OSError):
            _close_worker()
            raise OcrModelError("OCR 모델 준비와 패키지 설치를 확인하세요.") from None
        except Exception:
            _close_worker()
            raise
    def normalized(text):
        """공백·유니코드 차이를 없애 줄 단위로 비교한다."""
        return "".join(unicodedata.normalize("NFKC", text).split()).casefold()
    existing = {normalized(line) for line in existing_text.splitlines()}
    seen = set()
    result = []
    for line in lines:
        key = normalized(line)
        if key and key not in existing and key not in seen:
            result.append(line.strip())
            seen.add(key)
    return "\n".join(result)


def extract_image_text(data: bytes, existing_text: str = "") -> str:
    """I-01 OCR 실패 이미지만 건너뛰고 기존 문서 텍스트는 보존한다."""
    state = _budget.get()
    started = monotonic()
    try:
        if ocr_limit_reached():
            logger.warning("OCR 문서 처리 한도 또는 모델 준비 상태로 이미지를 건너뜁니다.")
            return ""
        with Image.open(io.BytesIO(data)) as image:
            if min(image.size) < config.OCR_MIN_SIDE:
                return ""
        if state:
            state["count"] += 1
        remaining = config.OCR_DOCUMENT_SECONDS - state["seconds"] if state else config.OCR_TIMEOUT_SECONDS
        return _extract_image_text(data, existing_text, min(config.OCR_TIMEOUT_SECONDS, remaining))
    except Exception as error:
        if state and isinstance(error, OcrModelError):
            state["unavailable"] = True
        reason = ("모델 준비·패키지 설치" if isinstance(error, OcrModelError)
                  else "처리 시간 한도" if isinstance(error, TimeoutError) else "이미지 형식·손상·크기")
        logger.warning("OCR 이미지 건너뜀 (%s): %s 확인이 필요합니다.", type(error).__name__, reason)
        return ""
    finally:
        if state:
            state["seconds"] += monotonic() - started


if __name__ == "__main__":
    _worker()
