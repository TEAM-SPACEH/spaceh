"""환경변수·API 키·저장 경로 설정. 값은 저장소 루트의 .env에서 읽는다."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DART_API_KEY = os.getenv("DART_API_KEY", "")

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "spaceh")

UPLOAD_DIR = ROOT_DIR / os.getenv("UPLOAD_DIR", "data/uploads")
CHROMA_DIR = ROOT_DIR / os.getenv("CHROMA_DIR", "data/chroma")
CHROMA_COLLECTION = "documents"
OCR_MODEL_DIR = ROOT_DIR / "data" / "ocr"
OCR_TIMEOUT_SECONDS = 120
OCR_MAX_PIXELS = 20_000_000
OCR_RENDER_DPI = 150
OCR_MIN_SIDE = 100
OCR_MAX_IMAGES = 200
OCR_DOCUMENT_SECONDS = 180

# S-01 검색 결과로 가져올 청크 수
SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
# S-06 하이브리드 검색 RRF 상수. 클수록 순위 차이가 점수에 덜 반영된다 (관례값 60).
HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))

SEED_DEFAULT_PASSWORD = os.getenv("SEED_DEFAULT_PASSWORD", "")
