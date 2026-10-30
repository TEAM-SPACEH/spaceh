"""I-01 최초 실행 전에 공개 OCR 모델만 내려받는다. 원본 문서는 사용하지 않는다."""

from core import config


def main() -> None:
    """I-01 한국어·영어 CPU 모델을 프로젝트 공통 경로에 준비한다."""
    import easyocr
    easyocr.Reader(["ko", "en"], gpu=False,
                   model_storage_directory=str(config.OCR_MODEL_DIR),
                   download_enabled=True, verbose=False)
    print("OCR models ready.")


if __name__ == "__main__":
    main()
