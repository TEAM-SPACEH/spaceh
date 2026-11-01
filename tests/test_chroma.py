"""core.chroma 테스트: 동시에 열고 닫아도 Chroma 내부 System 참조가 깨지지 않는지 확인한다.

Chroma의 생성(System 확인 → 참조 수 증가)과 종료(참조 수 감소 → System 제거) 사이에
1ms 지연을 넣어 겹치는 구간을 일부러 넓힌다. 잠금이 없으면 KeyError 등이 난다.
"""

import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from chromadb.api.shared_system_client import SharedSystemClient

from core.chroma import open_chroma_client

_create = SharedSystemClient._create_system_if_not_exists.__func__


def _slow_create(cls, identifier, settings):
    system = _create(cls, identifier, settings)
    time.sleep(0.001)
    return system


def _slow_release(cls, identifier):
    refcount = cls._decrement_refcount(identifier)
    time.sleep(0.001)
    if refcount <= 0:
        system = cls._identifier_to_system.pop(identifier, None)
        if system is not None:
            system.stop()


class OpenChromaClientTest(unittest.TestCase):
    def test_concurrent_open_close_does_not_break_shared_system(self):
        errors = []
        with tempfile.TemporaryDirectory() as path:
            def worker():
                for _ in range(15):
                    try:
                        with open_chroma_client(path) as client:
                            client.list_collections()
                    except Exception as error:  # 어떤 예외든 실패로 센다
                        errors.append(type(error).__name__)

            with patch.object(SharedSystemClient, "_create_system_if_not_exists", classmethod(_slow_create)), \
                    patch.object(SharedSystemClient, "_release_system", classmethod(_slow_release)):
                threads = [threading.Thread(target=worker) for _ in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
        self.assertEqual(errors, [])

    def test_client_closed_after_block_even_on_error(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(RuntimeError):
                with open_chroma_client(path) as client:
                    raise RuntimeError("검색 중 오류")
            self.assertTrue(client._closed)


if __name__ == "__main__":
    unittest.main()
