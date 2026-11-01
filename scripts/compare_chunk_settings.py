"""분리된 로컬 색인으로 청크 크기·오버랩을 비교한다. 기본 실행은 외부 전송 없는 준비다."""

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from scripts.evaluate_retrieval import (
    build_payload, chunk_body, digest, evaluate_question, normalized, source_snapshot,
    summarize, PROMPT_VERSION, SYSTEM_PROMPT,
)

LOGGER = logging.getLogger(__name__)
SIZE_CANDIDATES = (400, 800, 1200, 1600)
BASE = {"name": "BASE", "chunk_size": 800, "chunk_overlap": 150}
TOKEN_ENCODING = "cl100k_base"
TOKEN_BUDGET = 4000
APP_TOP_K = 10
BUDGET_TOP_K = 30


def configurations(stage: str, size: int | None = None) -> list[dict]:
    """확정한 두 단계 후보와 현재 기본값을 반환한다."""
    if stage == "size":
        candidates = [(n, n // 10) for n in SIZE_CANDIDATES]
    elif stage == "overlap" and size in SIZE_CANDIDATES:
        candidates = [(size, size * rate // 100) for rate in (0, 10, 20)]
    else:
        raise ValueError("오버랩 단계에는 1차에서 선택한 크기를 지정해야 합니다.")
    return [dict(BASE), *[
        {"name": f"C{n}_O{o}", "chunk_size": n, "chunk_overlap": o}
        for n, o in candidates if (n, o) != (BASE["chunk_size"], BASE["chunk_overlap"])
    ]]


def token_count(text: str, encoding) -> int:
    """특수 토큰처럼 보이는 문서 문자열도 일반 데이터로 센다."""
    return len(encoding.encode(text, disallowed_special=()))


def budget_prefix(chunks: list[dict], encoding, budget: int = TOKEN_BUDGET) -> list[dict]:
    """순위를 유지하고 출처 포함 총 토큰이 한도를 넘기기 직전에 멈춘다."""
    result = []
    for chunk in chunks:
        candidate = [*result, chunk]
        # 청크를 잇는 줄바꿈도 포함하며, 초과 청크를 건너뛰거나 자르지 않는다.
        if token_count("\n\n".join(c["text"] for c in candidate), encoding) > budget:
            break
        result = candidate
    return result


def load_dataset(root: Path) -> dict:
    """기존 12문항을 보존하면서 별도 검증된 개발 문항을 합친다."""
    folder = root / "docs" / "experiments"
    original = json.loads((folder / "chunk_questions_v2.json").read_text(encoding="utf-8"))
    additions = json.loads((folder / "chunk_questions_additional.json").read_text(encoding="utf-8"))
    dataset = {**original, "split": "development", "status": "prepared_not_evaluated",
               "questions": [*original["questions"], *additions["questions"]]}
    ids = [q["id"] for q in dataset["questions"]]
    doc_ids = {d["doc_id"] for d in dataset["documents"]}
    if len(ids) != len(set(ids)):
        raise ValueError("중복 질문 ID입니다.")
    for question in dataset["questions"]:
        build_payload(question, [])
        if (question["doc_id"] not in doc_ids
                or question["track"] not in {"chunking", "extraction_diagnostic"}):
            raise ValueError("문서 ID 또는 문항 구분이 올바르지 않습니다.")
    return dataset


def identity(dataset: dict) -> tuple[dict, dict, dict]:
    """실제 활성 관리자와 원본·색인·권한 스냅샷을 확인한다."""
    from app.auth.repositories.user_repository import find_user_by_employee_no
    found = find_user_by_employee_no("ADM-0001")
    if not found or not found["is_active"] or found["role"] != "super_admin":
        raise PermissionError("활성 ADM-0001 관리자 계정이 필요합니다.")
    user = {k: found[k] for k in ("id", "employee_no", "role", "company_id")}
    filters = {"doc_id": {"$in": [d["doc_id"] for d in dataset["documents"]]}}
    return user, filters, source_snapshot(dataset, user, filters)


def save_json(path: Path, value: dict) -> None:
    """실험 산출물만 로컬에 기록한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def source_signature(snapshot: dict) -> dict:
    """원본·권한·파서·마스킹·OCR 설정 변경 시 고정 블록 캐시를 분리한다."""
    from core import config
    paths = [*sorted((config.ROOT_DIR / "app/ingestion/parsers").glob("*.py")),
             *sorted((config.ROOT_DIR / "app/ingestion/preprocessing").glob("*.py"))]
    return {"snapshot": snapshot,
            "code": {str(p.relative_to(config.ROOT_DIR)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in paths},
            "ocr": {k: getattr(config, k) for k in (
                "OCR_TIMEOUT_SECONDS", "OCR_MAX_PIXELS", "OCR_RENDER_DPI", "OCR_MIN_SIDE",
                "OCR_MAX_IMAGES", "OCR_DOCUMENT_SECONDS")},
            "ocr_models": {p.name: {"size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
                           for p in sorted(config.OCR_MODEL_DIR.glob("*.pth"))}}


def freeze_sources(dataset: dict, user: dict, filters: dict, snapshot: dict,
                   folder: Path, signature: dict) -> dict:
    """모든 후보가 같은 추출 결과를 공유하도록 OCR 블록을 고정한다."""
    from app.ingestion.parsers.loader import load_document
    from app.ingestion.preprocessing.masking import mask_sensitive_data
    from app.permissions.services.permission_service import apply_rbac_filter, check_search_permission
    from app.search.repositories.chunk_repository import get_chunks
    from core.database import get_connection

    path = folder / "corpus.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["signature"] != signature or digest(saved["documents"]) != saved["blocks_sha256"]:
            raise ValueError("고정 블록 캐시가 입력과 일치하지 않습니다.")
        return saved
    allowed = get_chunks(apply_rbac_filter(user, filters))
    metadata_by_id = {}
    for chunk in allowed:
        metadata = chunk["metadata"]
        metadata_by_id.setdefault(metadata["doc_id"], {
            k: v for k, v in metadata.items()
            if k not in {"chunk_index", "page", "location", "section", "block_type"}})
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT doc_id, file_path FROM documents")
        paths = {r["doc_id"]: r["file_path"] for r in cursor.fetchall()}
    documents = []
    for source in dataset["documents"]:
        doc_id = source["doc_id"]
        metadata = metadata_by_id[doc_id]
        if not check_search_permission(user, metadata):
            raise PermissionError("원본 열람 권한이 없습니다.")
        started = perf_counter()
        blocks, mask_count = mask_sensitive_data(load_document(paths[doc_id]))
        documents.append({"doc_id": doc_id, "metadata": metadata, "blocks": blocks,
                          "masked_count": mask_count})
        LOGGER.info("Frozen %s: %d blocks (%.1fs)", doc_id, len(blocks), perf_counter() - started)
    if source_snapshot(dataset, user, filters) != snapshot:
        raise ValueError("추출 중 원본 또는 기존 색인이 변경됐습니다.")
    corpus = {"signature": signature, "documents": documents, "blocks_sha256": digest(documents)}
    save_json(path, corpus)
    return corpus


def make_chunks(corpus: dict, candidate: dict) -> list[dict]:
    """앱과 같은 청커에 후보 크기·오버랩만 전달한다."""
    from app.ingestion.preprocessing.chunker import split_into_chunks
    return [chunk for document in corpus["documents"]
            for chunk in split_into_chunks(document["blocks"], document["metadata"], candidate)]


def anchor_checks(dataset: dict, corpus: dict) -> list[dict]:
    """추가 문항의 원본 발췌가 지정 위치의 고정 추출 결과에 있는지 점검한다."""
    by_id = {d["doc_id"]: d for d in corpus["documents"]}
    checks = []
    for question in dataset["questions"]:
        anchors = question.get("source_anchors", [])
        if not anchors:
            continue  # 기존 문항의 검증 기록은 별도 보존한다.
        blocks = by_id[question["doc_id"]]["blocks"]
        text = normalized("\n".join(b["text"] for b in blocks
                                    if b["page"] in question["source"]["positions"]))
        missing = [a for a in anchors if normalized(a) not in text]
        checks.append({"question_id": question["id"], "ok": not missing, "missing": missing})
    return checks


def prepare(dataset: dict, corpus: dict, candidates: list[dict], encoding) -> dict:
    """API 없이 후보별 청크·토큰 수와 근거 추출 점검 결과를 산출한다."""
    stats = []
    unique_texts = set()
    for candidate in candidates:
        chunks = make_chunks(corpus, candidate)
        unique_texts.update(c["text"] for c in chunks)
        lengths = [token_count(c["text"], encoding) for c in chunks]
        stats.append({**candidate, "chunk_count": len(chunks),
                      "by_document": dict(Counter(c["metadata"]["doc_id"] for c in chunks)),
                      "embedding_input_tokens": sum(lengths), "max_chunk_tokens": max(lengths),
                      "max_body_chars": max(len(chunk_body(c["text"])) for c in chunks),
                      "over_size_chunks": sum(len(chunk_body(c["text"])) > candidate["chunk_size"] for c in chunks),
                      "chunks_sha256": digest(chunks)})
    return {"status": "prepared", "api_calls": 0, "dataset_sha256": digest(dataset),
            "blocks_sha256": corpus["blocks_sha256"], "token_encoding": TOKEN_ENCODING,
            "token_budget": TOKEN_BUDGET, "app_top_k": APP_TOP_K, "budget_top_k": BUDGET_TOP_K,
            "tracks": dict(Counter(q["track"] for q in dataset["questions"])),
            "settings": stats, "source_anchor_checks": anchor_checks(dataset, corpus),
            "unique_embedding_texts": len(unique_texts),
            "unique_embedding_input_tokens": sum(token_count(text, encoding) for text in unique_texts),
            "maximum_judgments": len(candidates) * len(dataset["questions"]) * 2 * 2,
            "limitations": ["개발 문항이며 최종 검증 세트가 아님", "문항 수보다 독립 근거 수가 적음"]}


@contextmanager
def experiment_search(index_path: Path, top_k: int, embedding):
    """실험 프로세스 안에서만 저장 경로·검색 개수·질문 임베딩을 바꾼다."""
    from core import config
    from app.search.services import search_service
    if index_path.resolve() == config.CHROMA_DIR.resolve():
        raise ValueError("앱 색인을 실험 경로로 사용할 수 없습니다.")
    with (patch.object(config, "CHROMA_DIR", index_path),
          patch.object(config, "SEARCH_TOP_K", top_k),
          patch.object(search_service, "_embed_query", side_effect=embedding)):
        yield search_service


def cached_embeddings(texts: list[str], client, folder: Path, model: str, encoding) -> tuple[list, dict]:
    """모델·본문이 같은 벡터만 재사용하고 실제 요청 토큰을 따로 센다."""
    from math import isfinite
    folder.mkdir(parents=True, exist_ok=True)
    keys = [digest({"model": model, "text": t}) for t in texts]
    missing = {key: text for key, text in zip(keys, texts) if not (folder / f"{key}.json").exists()}
    usage = {"requests": 0, "prompt_tokens": 0}
    items = list(missing.items())
    for start in range(0, len(items), 32):
        batch = items[start:start + 32]
        # 현재 청커의 긴 표 행도 보존하되 입력 한도 밖이면 조용히 자르지 않고 중단한다.
        if any(token_count(text, encoding) > 8191 for _, text in batch):
            raise ValueError("임베딩 입력 한도를 초과한 청크가 있습니다.")
        response = client.embeddings.create(model=model, input=[text for _, text in batch])
        if sorted(item.index for item in response.data) != list(range(len(batch))):
            raise ValueError("임베딩 응답 개수가 일치하지 않습니다.")
        for item in response.data:
            if not item.embedding or any(not isfinite(v) for v in item.embedding):
                raise ValueError("임베딩 응답이 유효하지 않습니다.")
            save_json(folder / f"{batch[item.index][0]}.json", {"embedding": item.embedding})
        usage["requests"] += 1
        usage["prompt_tokens"] += response.usage.prompt_tokens
        LOGGER.info("Embeddings cached: %d/%d", min(start + 32, len(items)), len(items))
    return [json.loads((folder / f"{k}.json").read_text(encoding="utf-8"))["embedding"]
            for k in keys], usage


def report_summary(records: list[dict]) -> dict:
    """설정·검색 방식·분량별로 집계하고 진단 문항은 분리한다."""
    return {name: {policy: summarize([r for r in records
                                    if r["setting"] == name and r["policy"] == policy])
                   for policy in ("tokens4000", "top10")}
            for name in sorted({r["setting"] for r in records})}


def manual_review_queue(records: list[dict]) -> list[dict]:
    """검토 판정과 설정 간 결과가 달라진 문항을 수동 확인 목록으로 남긴다."""
    groups = {}
    for record in records:
        key = (record["policy"], record["method"], record["question_id"])
        groups.setdefault(key, []).append(record)
    return [{"policy": key[0], "method": key[1], "question_id": key[2],
             "outcomes": {r["setting"]: r["outcome"] for r in items}}
            for key, items in sorted(groups.items())
            if len({r["outcome"] for r in items}) > 1
            or any(r["outcome"] == "review" for r in items)]


def record_key(record: dict) -> tuple:
    """재개할 때 설정·분량·검색·질문 조합을 중복 실행하지 않는다."""
    return tuple(record[k] for k in ("setting", "policy", "method", "question_id"))


def resume_report(path: Path, current: dict, questions: list[dict]) -> dict:
    """실험 입력과 모델이 같은 중단 결과만 이어받고 이전 기록을 보존한다."""
    if not path.exists():
        return current
    prior = json.loads(path.read_text(encoding="utf-8"))
    for key in ("stage", "preflight", "snapshot", "judge_model", "embedding_model",
                "prompt_version", "prompt_sha256", "hybrid_rrf_k", "hybrid_candidate_factor"):
        if prior[key] != current[key]:
            raise ValueError("재개할 실험 입력이 기존 결과와 다릅니다.")
    if prior["status"] not in {"interrupted", "complete_pending_manual_review"}:
        raise ValueError("중단 또는 완료된 실험만 이어받을 수 있습니다.")
    expected = {(setting["name"], policy, method, question["id"])
                for setting in current["preflight"]["settings"] for question in questions
                for policy in ("tokens4000", "top10") for method in ("vector", "hybrid")}
    keys = [record_key(r) for r in prior["records"]]
    if len(keys) != len(set(keys)) or not set(keys).issubset(expected):
        raise ValueError("기존 결과에 중복 또는 알 수 없는 조합이 있습니다.")
    prior.setdefault("attempts", [{"created_at_utc": prior["created_at_utc"],
                                   "runner_sha256": prior["runner_sha256"]}])
    if prior["status"] == "interrupted":
        prior.setdefault("interruptions", []).append({
            k: prior[k] for k in ("error_type", "error_context", "error_frames") if k in prior})
        prior["attempts"].append({"created_at_utc": current["created_at_utc"],
                                  "runner_sha256": current["runner_sha256"],
                                  "completed_before_resume": len(keys)})
        prior["status"] = "running"
    for key in ("error_type", "error_context", "error_frames"):
        prior.pop(key, None)
    return prior


def experiment_index_path(folder: Path, setting_name: str, embedding_model: str) -> Path:
    """모델 식별자를 해시한 경로로 모델별 실험 벡터를 격리한다."""
    return folder / "indexes" / digest({"embedding_model": embedding_model})[:16] / setting_name


def index_matches(index_path: Path, chunks: list[dict]) -> bool:
    """동일한 실험 청크의 기존 색인은 재삽입하지 않아 검색 순서를 유지한다."""
    from chromadb.errors import NotFoundError
    from core import config
    from core.chroma import open_chroma_client
    if not (index_path / "chroma.sqlite3").is_file():
        return False
    with open_chroma_client(index_path) as client:
        try:
            collection = client.get_collection(config.CHROMA_COLLECTION)
        except NotFoundError:
            return False
        saved = collection.get(include=["documents", "metadatas"])
    existing = [{"chunk_id": cid, "text": text, "metadata": metadata}
                for cid, text, metadata in zip(saved["ids"], saved["documents"], saved["metadatas"])]
    return digest(sorted(existing, key=lambda c: c["chunk_id"])) == digest(sorted(chunks, key=lambda c: c["chunk_id"]))


def evaluate(dataset: dict, corpus: dict, preflight: dict, folder: Path,
             user: dict, filters: dict, snapshot: dict, encoding, stage: str) -> dict:
    """명시적 전송 옵션이 있을 때만 실험 색인·API 평가를 실행한다."""
    from openai import OpenAI
    from core import config
    from app.ingestion.indexing.indexer import DocumentIndexer
    from app.permissions.services.permission_service import apply_rbac_filter

    if any(not c["ok"] for c in preflight["source_anchor_checks"]):
        raise ValueError("추가 질문의 추출 근거에 미해결 항목이 있습니다.")
    if not config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 필요합니다.")
    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=90, max_retries=0)
    cache = config.ROOT_DIR / ".venv/chunk_experiment/cache"
    questions = dataset["questions"]
    usage = {"requests": 0, "prompt_tokens": 0}
    records = []
    report = {"status": "running", "stage": stage, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "preflight": preflight, "snapshot": snapshot, "records": records,
              "judge_model": config.LLM_MODEL, "embedding_model": config.EMBEDDING_MODEL,
              "prompt_version": PROMPT_VERSION, "prompt_sha256": digest(SYSTEM_PROMPT),
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "hybrid_rrf_k": config.HYBRID_RRF_K, "hybrid_candidate_factor": 3,
              "embedding_usage_this_run": usage}
    result_path = folder / f"results_{stage}_{digest(preflight)[:12]}.json"
    report = resume_report(result_path, report, questions)
    if report["status"] == "complete_pending_manual_review":
        LOGGER.info("Already complete: %s", result_path)
        return report
    records = report["records"]
    usage = report["embedding_usage_this_run"]
    completed = {record_key(r) for r in records}
    active = {"stage": "query_embeddings"}

    def save():
        report["summary"] = report_summary(records)
        report["by_kind"] = {kind: report_summary([r for r in records if r["kind"] == kind])
                             for kind in sorted({r["kind"] for r in records})}
        report["by_document"] = {doc_id: report_summary([r for r in records if r["doc_id"] == doc_id])
                                 for doc_id in sorted({r["doc_id"] for r in records})}
        report["manual_review_queue"] = manual_review_queue(records)
        save_json(result_path, report)

    try:
        save()
        qvectors, actual = cached_embeddings([q["question"] for q in questions], client,
                                            cache / "embeddings", config.EMBEDDING_MODEL, encoding)
        for key, value in actual.items():
            usage[key] += value
        lookup = {q["question"].strip(): vector for q, vector in zip(questions, qvectors)}
        for candidate in preflight["settings"]:
            expected = {(candidate["name"], policy, method, q["id"]) for q in questions
                        for policy in ("tokens4000", "top10") for method in ("vector", "hybrid")}
            if expected.issubset(completed):
                LOGGER.info("Completed setting preserved: %s", candidate["name"])
                continue
            active = {"setting": candidate["name"], "stage": "index"}
            chunks = make_chunks(corpus, candidate)
            if digest(chunks) != candidate["chunks_sha256"]:
                raise ValueError("청킹 결과가 준비 단계와 다릅니다.")
            vectors, actual = cached_embeddings([c["text"] for c in chunks], client,
                                                cache / "embeddings", config.EMBEDDING_MODEL, encoding)
            for key, value in actual.items():
                usage[key] += value
            index_path = experiment_index_path(folder, candidate["name"], config.EMBEDDING_MODEL)
            if index_path.resolve().is_relative_to(config.CHROMA_DIR.resolve()):
                raise ValueError("기존 앱 색인 안에 실험 색인을 만들 수 없습니다.")
            if not index_matches(index_path, chunks):
                with DocumentIndexer({"path": index_path}) as indexer:
                    for doc_id in [d["doc_id"] for d in dataset["documents"]]:
                        selected = [(c, v) for c, v in zip(chunks, vectors) if c["metadata"]["doc_id"] == doc_id]
                        indexer.index_chunks(doc_id, [c for c, _ in selected], [v for _, v in selected])
            # 기존 서비스가 검색 후보를 가져오기 전에 권한 조건을 적용한다.
            apply_rbac_filter(user, filters)
            for policy, top_k in (("tokens4000", BUDGET_TOP_K), ("top10", APP_TOP_K)):
                with experiment_search(index_path, top_k, lambda query: lookup[query.strip()]) as service:
                    methods = {"vector": service.search_documents, "hybrid": service.hybrid_search}
                    for question in questions:
                        for method, search in methods.items():
                            key = (candidate["name"], policy, method, question["id"])
                            if key in completed:
                                continue
                            active = {"setting": candidate["name"], "policy": policy,
                                      "method": method, "question_id": question["id"]}
                            started = perf_counter()
                            retrieved = search(question["question"], filters, user, audit=False)
                            elapsed = perf_counter() - started
                            evidence = budget_prefix(retrieved, encoding) if policy == "tokens4000" else retrieved
                            judgment = evaluate_question(question, evidence, config.LLM_MODEL, client, cache / "judgments")
                            records.append({"setting": candidate["name"], "policy": policy,
                                            "method": method, "question_id": question["id"],
                                            "doc_id": question["doc_id"],
                                            "track": question["track"], "kind": question["kind"],
                                            "retrieval_seconds": elapsed,
                                            "context_tokens": token_count("\n\n".join(c["text"] for c in evidence), encoding),
                                            "retrieved_chunk_ids": [c["chunk_id"] for c in retrieved],
                                            "chunks": evidence, **judgment})
                            completed.add(key)
                            save()
                            LOGGER.info("%s %s %s %s: %s", candidate["name"], policy,
                                        method, question["id"], judgment["outcome"])
        if source_snapshot(dataset, user, filters) != snapshot:
            report["status"] = "invalid_corpus_changed"
            save()
            raise ValueError("실행 중 기존 색인이 변경됐습니다.")
        report["status"] = "complete_pending_manual_review"
        save()
    except Exception as exc:
        if report["status"] == "running":
            report["status"] = "interrupted"
        report["error_type"] = type(exc).__name__
        report["error_context"] = active
        import traceback
        report["error_frames"] = [{"file": Path(f.filename).name, "line": f.lineno,
                                    "function": f.name} for f in traceback.extract_tb(exc.__traceback__)]
        save()
        raise
    LOGGER.info("Results: %s", result_path)
    return report


def main() -> int:
    """기본은 로컬 준비이며 API 전송은 별도 플래그로 구분한다."""
    from core import config
    import tiktoken
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("size", "overlap"), default="size")
    parser.add_argument("--selected-size", type=int, choices=SIZE_CANDIDATES,
                        help="1차 결과를 수동 확인한 뒤 선택한 크기")
    parser.add_argument("--send-to-openai", action="store_true",
                        help="고정 문서 청크·질문을 임베딩하고 질문·정답·검색 근거를 OpenAI에 전송")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for name in ("httpx", "httpcore", "chromadb", "easyocr"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        candidates = configurations(args.stage, args.selected_size)
        dataset = load_dataset(config.ROOT_DIR)
        user, filters, snapshot = identity(dataset)
        signature = source_signature(snapshot)
        folder = config.ROOT_DIR / ".venv/chunk_experiment" / digest(signature)[:20]
        corpus = freeze_sources(dataset, user, filters, snapshot, folder, signature)
        encoding = tiktoken.get_encoding(TOKEN_ENCODING)
        preflight = prepare(dataset, corpus, candidates, encoding)
        save_json(folder / f"preflight_{args.stage}.json", preflight)
        LOGGER.info("Prepared: %s", folder)
        for setting in preflight["settings"]:
            LOGGER.info("%s: %d chunks, %d input tokens", setting["name"],
                        setting["chunk_count"], setting["embedding_input_tokens"])
        missing = [c["question_id"] for c in preflight["source_anchor_checks"] if not c["ok"]]
        LOGGER.info("Questions: %s; unresolved source checks: %s", preflight["tracks"], missing)
        if missing:
            return 1
        if args.send_to_openai:
            evaluate(dataset, corpus, preflight, folder, user, filters, snapshot, encoding, args.stage)
        else:
            LOGGER.info("No embedding or judgment API calls were made.")
    except Exception as exc:
        LOGGER.error("Stopped (%s); sensitive error details are not logged.", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
