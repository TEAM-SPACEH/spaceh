"""공통 Chroma 연결. Chroma(PersistentClient)는 반드시 open_chroma_client()로만 연다.

Chroma 1.5.9는 같은 경로의 클라이언트끼리 내부 System을 참조 수로 공유한다. 그런데
생성(System 확인 → 참조 수 증가)과 close()(참조 수 감소 → System 제거)가 각각 두 단계로 나뉘어
있고 그 사이에 잠금이 없다. 두 검색이 동시에 열고 닫으면 생성 쪽이 제거될 System을 잡아
KeyError가 날 수 있으므로, 생성과 close()를 이 모듈의 잠금 하나로 직렬화한다.
검색·질의 자체는 잠금 밖에서 실행되어 서로 기다리지 않는다.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI

from core import config

# 같은 프로세스의 모든 Chroma 클라이언트 생성·종료가 이 잠금을 쓴다 (경로가 달라도 같이 써서 단순하게).
_CLIENT_LOCK = threading.Lock()


@contextmanager
def open_chroma_client(path: str | Path | None = None) -> Iterator[ClientAPI]:
    """Chroma 클라이언트를 열고, 블록이 끝나거나 예외가 나면 닫는다 (Windows 파일 잠금 해제)."""
    # 기본 경로는 호출할 때 읽는다 (테스트가 config.CHROMA_DIR을 바꿀 수 있게).
    target = str(path if path is not None else config.CHROMA_DIR)
    with _CLIENT_LOCK:
        client = chromadb.PersistentClient(path=target)
    try:
        yield client
    finally:
        with _CLIENT_LOCK:
            client.close()
