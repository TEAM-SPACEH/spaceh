"""I-01 공통 이미지 OCR. CPU 작업을 별도 프로세스에서 실행한다."""

import atexit
import io
import multiprocessing
import threading
import unicodedata

from PIL import Image

from core import config

_lock = threading.Lock()
_process = None
_connection = None


def _worker(connection, model_dir):
    """모델은 프로세스당 한 번만 읽고 원문·오류 원문은 출력하지 않는다."""
    try:
        import easyocr
        reader = None
        while True:
            data = connection.recv_bytes()
            if reader is None:
                reader = easyocr.Reader(
                    ["ko", "en"], gpu=False, model_storage_directory=model_dir,
                    download_enabled=False, verbose=False,
                )
            lines = reader.readtext(data, detail=0, paragraph=False, workers=0)
            connection.send((True, lines))
    except Exception:
        connection.send((False, []))
    finally:
        connection.close()


def _close_worker():
    global _process, _connection
    if _process is not None:
        if _process.is_alive():
            _process.terminate()
        _process.join(timeout=5)
        _process.close()
    if _connection is not None:
        _connection.close()
    _process = _connection = None


atexit.register(_close_worker)


def extract_image_text(data: bytes, existing_text: str = "") -> str:
    """I-01 이미지 글자를 읽고 기존 텍스트와 같은 OCR 줄은 제외한다."""
    global _process, _connection
    # 디코딩 크기를 검사해 비정상 이미지로 인한 메모리 사용을 제한한다.
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > config.OCR_MAX_PIXELS:
            raise ValueError("OCR 이미지 크기 한도를 초과했습니다.")
    with _lock:
        if _process is None or not _process.is_alive():
            _close_worker()
            context = multiprocessing.get_context("spawn")
            _connection, child = context.Pipe()
            _process = context.Process(
                target=_worker, args=(child, str(config.OCR_MODEL_DIR)), daemon=True,
            )
            _process.start()
            child.close()
        try:
            _connection.send_bytes(data)
            if not _connection.poll(config.OCR_TIMEOUT_SECONDS):
                raise TimeoutError("OCR 처리 시간 한도를 초과했습니다.")
            success, lines = _connection.recv()
            if not success:
                raise RuntimeError("OCR 모델 준비와 패키지 설치를 확인하세요.")
        except Exception:
            _close_worker()
            raise
    def normalized(text):
        return "".join(unicodedata.normalize("NFKC", text).split()).casefold()
    existing = normalized(existing_text)
    seen = set()
    result = []
    for line in lines:
        key = normalized(line)
        if key and key not in existing and key not in seen:
            result.append(line.strip())
            seen.add(key)
    return "\n".join(result)
