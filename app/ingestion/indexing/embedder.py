"""I-02 마스킹·청킹이 끝난 텍스트를 검색과 같은 모델로 임베딩한다."""

from math import isfinite

from langchain_openai import OpenAIEmbeddings

from core import config


class DocumentEmbedder:
    """I-02 문서 청크 순서에 대응하는 임베딩 벡터를 생성한다."""

    def __init__(self) -> None:
        """검색과 같은 모델·API 키를 사용하는 클라이언트를 보관한다."""
        # 길이 검사 기본 기능을 유지하고, 최대 길이 입력도 요청당 토큰 합계를 넘지 않게 한다.
        self._embeddings = OpenAIEmbeddings(
            model=config.EMBEDDING_MODEL, api_key=config.OPENAI_API_KEY,
            chunk_size=32,
        )

    def embed_chunks(self, chunks: list[dict]) -> list[list[float]]:
        """I-02 청크 텍스트를 입력 순서의 벡터 목록으로 변환하고 오류는 호출자에 알린다."""
        if not isinstance(chunks, list):
            raise ValueError("청크는 dict 목록이어야 합니다.")
        texts = []
        for chunk in chunks:
            if (not isinstance(chunk, dict)
                    or not isinstance(chunk.get("text"), str)
                    or not chunk["text"].strip()):
                raise ValueError("각 청크에는 비어 있지 않은 text 문자열이 필요합니다.")
            texts.append(chunk["text"])
        if not texts:
            return []
        # 직접 자르거나 누락시키지 않고 LangChain의 긴 입력 분할·가중 평균을 사용한다.
        vectors = self._embeddings.embed_documents(texts)
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise ValueError("임베딩 벡터 개수 또는 내용이 청크와 맞지 않습니다.")
        dimension = len(vectors[0])
        if any(len(vector) != dimension
               or any(type(value) not in (int, float) or not isfinite(value)
                      for value in vector) for vector in vectors):
            raise ValueError("임베딩 벡터의 차원 또는 숫자 값이 올바르지 않습니다.")
        return vectors
