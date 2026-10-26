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
