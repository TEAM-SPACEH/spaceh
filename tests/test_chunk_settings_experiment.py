"""청킹 비교 도구의 후보·분량·격리·캐시를 외부 API 없이 검증한다."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts import compare_chunk_settings as experiment


class CharacterEncoding:
    def encode(self, text, *, disallowed_special):
        return list(text)


def corpus():
    return {"blocks_sha256": "fixture", "documents": [{
        "doc_id": "doc", "metadata": {
            "doc_id": "doc", "company_id": "MVX", "company_name": "회사",
            "title": "제목", "doc_type": "report", "access_level": "public",
            "is_group_shared": False, "file_name": "sample.pdf", "file_format": "pdf",
            "source_type": "internal"},
        "blocks": [{"text": "내용" * 1100, "page": 1, "location": "p.1",
                    "section": "", "block_type": "text"}]}]}


class ConfigurationTest(unittest.TestCase):
    def test_size_candidates_use_ten_percent_and_preserve_base(self):
        candidates = experiment.configurations("size")
        self.assertEqual(candidates[0], experiment.BASE)
        self.assertEqual([(c["chunk_size"], c["chunk_overlap"]) for c in candidates[1:]],
                         [(400, 40), (800, 80), (1200, 120), (1600, 160)])

    def test_overlap_candidates_use_chosen_size(self):
        candidates = experiment.configurations("overlap", 1200)
        self.assertEqual([(c["chunk_size"], c["chunk_overlap"]) for c in candidates[1:]],
                         [(1200, 0), (1200, 120), (1200, 240)])

    def test_overlap_requires_valid_prior_choice(self):
        for size in (None, 0, 900):
            with self.assertRaises(ValueError):
                experiment.configurations("overlap", size)

    def test_dataset_has_thirty_comparison_and_four_diagnostic_questions(self):
        dataset = experiment.load_dataset(Path(__file__).resolve().parent.parent)
        self.assertEqual(len(dataset["questions"]), 34)
        self.assertEqual(sum(q["track"] == "chunking" for q in dataset["questions"]), 30)
        self.assertEqual(sum(q["track"] == "extraction_diagnostic" for q in dataset["questions"]), 4)


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.encoding = CharacterEncoding()

    def test_exact_limit_includes_chunk_separators(self):
        chunks = [{"text": "abcd"}, {"text": "efgh"}]
        self.assertEqual(experiment.budget_prefix(chunks, self.encoding, 10), chunks)
        self.assertEqual(experiment.budget_prefix(chunks, self.encoding, 9), chunks[:1])

    def test_does_not_skip_or_truncate_oversized_first_chunk(self):
        chunks = [{"text": "abcdef"}, {"text": "x"}]
        self.assertEqual(experiment.budget_prefix(chunks, self.encoding, 5), [])

    def test_counts_source_header_and_preserves_originals(self):
        chunks = [{"text": "[출처]\n본문"}]
        before = deepcopy(chunks)
        self.assertEqual(experiment.budget_prefix(chunks, self.encoding, 2), [])
        self.assertEqual(chunks, before)

    def test_empty_candidates(self):
        self.assertEqual(experiment.budget_prefix([], self.encoding), [])


class PreparationTest(unittest.TestCase):
    def test_actual_chunker_changes_size_and_does_not_mutate_frozen_input(self):
        frozen = corpus()
        before = deepcopy(frozen)
        small = experiment.make_chunks(frozen, {"chunk_size": 400, "chunk_overlap": 40})
        large = experiment.make_chunks(frozen, {"chunk_size": 1600, "chunk_overlap": 160})
        self.assertGreater(len(small), len(large))
        self.assertEqual(frozen, before)

    def test_anchors_only_match_requested_source_position(self):
        question = {"id": "Q", "doc_id": "doc", "source_anchors": ["없는 내용"],
                    "source": {"positions": [1]}}
        checks = experiment.anchor_checks({"questions": [question]}, corpus())
        self.assertFalse(checks[0]["ok"])
        question["source_anchors"] = ["내용"]
        self.assertTrue(experiment.anchor_checks({"questions": [question]}, corpus())[0]["ok"])
        question["source"]["positions"] = [2]
        self.assertFalse(experiment.anchor_checks({"questions": [question]}, corpus())[0]["ok"])

    def test_prepare_reports_full_corpus_cost_without_api(self):
        dataset = {"questions": [{"id": "Q", "track": "chunking"}]}
        stats = experiment.prepare(dataset, corpus(), experiment.configurations("size"), CharacterEncoding())
        self.assertEqual(stats["api_calls"], 0)
        self.assertEqual(stats["maximum_judgments"], 20)
        self.assertEqual(len(stats["settings"]), 5)
        self.assertTrue(all(s["embedding_input_tokens"] > 0 for s in stats["settings"]))

    def test_setting_policy_and_diagnostic_counts_stay_separate(self):
        records = [
            {"setting": "A", "policy": "tokens4000", "method": "vector", "track": "chunking", "outcome": "pass"},
            {"setting": "A", "policy": "top10", "method": "vector", "track": "chunking", "outcome": "fail"},
            {"setting": "B", "policy": "tokens4000", "method": "hybrid", "track": "extraction_diagnostic", "outcome": "review"},
        ]
        summary = experiment.report_summary(records)
        self.assertEqual(summary["A"]["tokens4000"]["vector"]["chunking"]["pass"], 1)
        self.assertEqual(summary["A"]["top10"]["vector"]["chunking"]["pass"], 0)
        self.assertEqual(summary["B"]["tokens4000"]["hybrid"]["chunking"]["total"], 0)


class IsolationTest(unittest.TestCase):
    def test_index_path_separates_models_and_keeps_same_model_stable(self):
        folder = Path(".venv/fixture")
        first = experiment.experiment_index_path(folder, "BASE", "model-a")
        self.assertEqual(first, experiment.experiment_index_path(folder, "BASE", "model-a"))
        self.assertNotEqual(first, experiment.experiment_index_path(folder, "BASE", "model-b"))
        self.assertNotEqual(first, experiment.experiment_index_path(folder, "C800_O80", "model-a"))
        self.assertNotEqual(first, folder / "indexes" / "BASE")
        nested_model = experiment.experiment_index_path(folder, "BASE", "vendor/model")
        self.assertEqual(len(nested_model.relative_to(folder).parts), 3)

    def test_different_models_in_new_stage_do_not_reuse_same_dimension_vectors(self):
        from core import config
        from core.chroma import open_chroma_client
        from app.ingestion.indexing.indexer import DocumentIndexer
        frozen = corpus()
        question = {"id": "Q", "doc_id": "doc", "question": "내용",
                    "expected_answer": "내용", "required_facts": ["내용"],
                    "track": "chunking", "kind": "text"}
        dataset = {"documents": [{"doc_id": "doc"}], "questions": [question]}
        preflight = experiment.prepare(dataset, frozen, [experiment.BASE], CharacterEncoding())
        user = {"id": 1, "role": "super_admin", "company_id": None}
        filters = {"doc_id": {"$in": ["doc"]}}

        def vectors(texts, _client, _folder, model, _encoding):
            value = [1.0, 0.0] if model == "model-a" else [0.0, 1.0]
            return [value for _ in texts], {"requests": 0, "prompt_tokens": 0}

        with (TemporaryDirectory() as directory,
              patch.object(config, "OPENAI_API_KEY", "synthetic-test-key"),
              patch("openai.OpenAI") as api,
              patch.object(experiment, "cached_embeddings", side_effect=vectors),
              patch.object(experiment, "source_snapshot", return_value={}),
              patch.object(experiment, "evaluate_question", return_value={"outcome": "pass", "facts": []}),
              patch("app.ingestion.indexing.indexer.DocumentIndexer", wraps=DocumentIndexer) as indexer):
            folder = Path(directory)
            for stage, model in (("size", "model-a"), ("overlap", "model-b")):
                with patch.object(config, "EMBEDDING_MODEL", model):
                    result = experiment.evaluate(dataset, frozen, preflight, folder, user,
                                                 filters, {}, CharacterEncoding(), stage)
                    self.assertEqual(result["status"], "complete_pending_manual_review")
                path = experiment.experiment_index_path(folder, "BASE", model)
                with open_chroma_client(path) as client:
                    saved = client.get_collection(config.CHROMA_COLLECTION).get(include=["embeddings"])
                expected = [1.0, 0.0] if model == "model-a" else [0.0, 1.0]
                self.assertEqual(saved["embeddings"].tolist(),
                                 [expected] * preflight["settings"][0]["chunk_count"])
            self.assertEqual(indexer.call_count, 2)
            api.return_value.embeddings.create.assert_not_called()
            api.return_value.chat.completions.create.assert_not_called()

    def test_resume_skips_finished_judgments_and_preserves_existing_index(self):
        from core import config
        from app.ingestion.indexing.indexer import DocumentIndexer
        frozen = corpus()
        question = {"id": "Q", "doc_id": "doc", "question": "내용",
                    "expected_answer": "내용", "required_facts": ["내용"],
                    "track": "chunking", "kind": "text"}
        dataset = {"documents": [{"doc_id": "doc"}], "questions": [question]}
        preflight = experiment.prepare(dataset, frozen, experiment.configurations("size")[:2], CharacterEncoding())
        user = {"id": 1, "role": "super_admin", "company_id": None}
        filters = {"doc_id": {"$in": ["doc"]}}

        def vectors(texts, *_):
            return [[1.0, 0.0] for _ in texts], {"requests": 0, "prompt_tokens": 0}

        with (TemporaryDirectory() as directory,
              patch.object(config, "OPENAI_API_KEY", "synthetic-test-key"),
              patch("openai.OpenAI"),
              patch.object(experiment, "cached_embeddings", side_effect=vectors),
              patch.object(experiment, "source_snapshot", return_value={}),
              patch("app.ingestion.indexing.indexer.DocumentIndexer", wraps=DocumentIndexer) as indexer):
            folder = Path(directory)
            with patch.object(experiment, "evaluate_question", side_effect=[
                    {"outcome": "pass", "facts": []}, RuntimeError("synthetic")]) as judge:
                with self.assertRaises(RuntimeError):
                    experiment.evaluate(dataset, frozen, preflight, folder, user, filters, {}, CharacterEncoding(), "size")
                self.assertEqual(judge.call_count, 2)
            with patch.object(experiment, "evaluate_question", return_value={"outcome": "pass", "facts": []}) as judge:
                report = experiment.evaluate(dataset, frozen, preflight, folder, user, filters, {}, CharacterEncoding(), "size")
                self.assertEqual(judge.call_count, 7)
            self.assertEqual(len(report["records"]), 8)
            self.assertEqual(indexer.call_count, 2)
            self.assertEqual(report["attempts"][-1]["completed_before_resume"], 1)
            self.assertEqual(report["interruptions"][0]["error_context"]["method"], "hybrid")
            prior = deepcopy(report)
            with patch.object(experiment, "cached_embeddings") as embed:
                done = experiment.evaluate(dataset, frozen, preflight, folder, user, filters, {}, CharacterEncoding(), "size")
                self.assertEqual(done, prior)
                embed.assert_not_called()

    def test_api_error_leaves_interrupted_record_not_retrieval_failure(self):
        from core import config
        with (TemporaryDirectory() as directory,
              patch.object(config, "OPENAI_API_KEY", "synthetic-test-key"),
              patch("openai.OpenAI"),
              patch.object(experiment, "cached_embeddings", side_effect=RuntimeError("synthetic"))):
            folder = Path(directory)
            with self.assertRaises(RuntimeError):
                experiment.evaluate({"questions": [{"question": "test"}]}, {},
                                    {"source_anchor_checks": []}, folder, {}, {}, {}, CharacterEncoding(), "size")
            saved = json.loads(next(folder.glob("results_*.json")).read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "interrupted")
            self.assertEqual(saved["records"], [])
            self.assertEqual(saved["error_type"], "RuntimeError")

    def test_real_experiment_index_and_search_without_external_api(self):
        from core import config
        from core.chroma import open_chroma_client
        original_path = config.CHROMA_DIR
        frozen = corpus()
        question = {"id": "Q", "doc_id": "doc", "question": "내용",
                    "expected_answer": "내용", "required_facts": ["내용"],
                    "track": "chunking", "kind": "text"}
        dataset = {"documents": [{"doc_id": "doc"}], "questions": [question]}
        user = {"id": 1, "role": "super_admin", "company_id": None}
        filters = {"doc_id": {"$in": ["doc"]}}
        preflight = experiment.prepare(dataset, frozen, experiment.configurations("size")[:2], CharacterEncoding())

        def vectors(texts, *_):
            return [[1.0, 0.0] for _ in texts], {"requests": 0, "prompt_tokens": 0}

        with (TemporaryDirectory() as directory,
              patch.object(config, "OPENAI_API_KEY", "synthetic-test-key"),
              patch("openai.OpenAI") as api,
              patch.object(experiment, "cached_embeddings", side_effect=vectors),
              patch.object(experiment, "evaluate_question", return_value={"outcome": "pass", "facts": []}),
              patch.object(experiment, "source_snapshot", return_value={})):
            folder = Path(directory)
            report = experiment.evaluate(dataset, frozen, preflight, folder, user, filters, {}, CharacterEncoding(), "size")
            self.assertEqual(report["status"], "complete_pending_manual_review")
            self.assertEqual(len(report["records"]), 8)
            self.assertTrue(all(r["chunks"] for r in report["records"]))
            index_path = experiment.experiment_index_path(folder, "BASE", config.EMBEDDING_MODEL)
            with open_chroma_client(index_path) as client:
                self.assertEqual(client.get_collection(config.CHROMA_COLLECTION).count(),
                                 preflight["settings"][0]["chunk_count"])
            api.return_value.embeddings.create.assert_not_called()
            api.return_value.chat.completions.create.assert_not_called()
        self.assertEqual(config.CHROMA_DIR, original_path)

    def test_search_uses_temporary_path_and_restores_config_after_error(self):
        from core import config
        original_path, original_k = config.CHROMA_DIR, config.SEARCH_TOP_K
        with self.assertRaises(RuntimeError):
            with experiment.experiment_search(Path(".venv/fixture_index"), 30, lambda _: [1.0]) as service:
                self.assertEqual(config.SEARCH_TOP_K, 30)
                self.assertEqual(config.CHROMA_DIR, Path(".venv/fixture_index"))
                self.assertEqual(service._embed_query("q"), [1.0])
                raise RuntimeError("test")
        self.assertEqual((config.CHROMA_DIR, config.SEARCH_TOP_K), (original_path, original_k))

    def test_app_index_is_rejected(self):
        from core import config
        with self.assertRaises(ValueError):
            with experiment.experiment_search(config.CHROMA_DIR, 10, lambda _: []):
                self.fail("앱 색인은 실험 대상으로 사용할 수 없습니다.")

    def test_embedding_cache_deduplicates_text_and_invalidates_model(self):
        client = MagicMock()
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.0])],
            usage=SimpleNamespace(prompt_tokens=7))
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            vectors, usage = experiment.cached_embeddings(["same", "same"], client, folder, "model-a", CharacterEncoding())
            self.assertEqual(vectors, [[1.0, 0.0], [1.0, 0.0]])
            self.assertEqual(usage["requests"], 1)
            experiment.cached_embeddings(["same"], client, folder, "model-a", CharacterEncoding())
            self.assertEqual(client.embeddings.create.call_count, 1)
            experiment.cached_embeddings(["same"], client, folder, "model-b", CharacterEncoding())
            self.assertEqual(client.embeddings.create.call_count, 2)

    def test_long_embedding_is_not_silently_truncated(self):
        client = MagicMock()
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            experiment.cached_embeddings(["x" * 8192], client, Path(directory), "m", CharacterEncoding())
        client.embeddings.create.assert_not_called()

    def test_default_command_never_constructs_api_client_or_evaluates(self):
        from core import config
        frozen = corpus()
        dataset = {"questions": [{"id": "Q", "track": "chunking"}]}
        with (TemporaryDirectory() as directory,
              patch.object(config, "ROOT_DIR", Path(directory)),
              patch.object(experiment, "load_dataset", return_value=dataset),
              patch.object(experiment, "identity", return_value=({}, {}, {})),
              patch.object(experiment, "source_signature", return_value={}),
              patch.object(experiment, "freeze_sources", return_value=frozen),
              patch("tiktoken.get_encoding", return_value=CharacterEncoding()),
              patch.object(experiment, "evaluate") as evaluate,
              patch("openai.OpenAI") as client,
              patch("sys.argv", ["compare_chunk_settings"])):
            self.assertEqual(experiment.main(), 0)
            evaluate.assert_not_called()
            client.assert_not_called()


class ReviewQueueTest(unittest.TestCase):
    def test_resume_refuses_changed_models_or_inputs(self):
        current = {"stage": "size", "preflight": {"settings": [{"name": "BASE"}]},
                   "snapshot": {}, "judge_model": "model-a", "embedding_model": "embed-a",
                   "prompt_version": "p", "prompt_sha256": "h", "hybrid_rrf_k": 60,
                   "hybrid_candidate_factor": 3}
        prior = {**current, "judge_model": "model-b", "status": "interrupted", "records": []}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            experiment.save_json(path, prior)
            with self.assertRaises(ValueError):
                experiment.resume_report(path, current, [{"id": "Q"}])

    def test_resume_refuses_duplicate_combinations(self):
        current = {"stage": "size", "preflight": {"settings": [{"name": "BASE"}]},
                   "snapshot": {}, "judge_model": "m", "embedding_model": "e",
                   "prompt_version": "p", "prompt_sha256": "h", "hybrid_rrf_k": 60,
                   "hybrid_candidate_factor": 3}
        record = {"setting": "BASE", "policy": "top10", "method": "vector", "question_id": "Q"}
        prior = {**current, "status": "interrupted", "records": [record, record]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            experiment.save_json(path, prior)
            with self.assertRaises(ValueError):
                experiment.resume_report(path, current, [{"id": "Q"}])

    def test_differences_and_review_are_flagged_but_uniform_pass_is_not(self):
        records = [{"setting": name, "policy": "tokens4000", "method": "vector",
                    "question_id": question, "outcome": outcome}
                   for question, name, outcome in [("Q1", "A", "pass"), ("Q1", "B", "fail"),
                                                    ("Q2", "A", "review"), ("Q3", "A", "pass")]]
        self.assertEqual([r["question_id"] for r in experiment.manual_review_queue(records)], ["Q1", "Q2"])


if __name__ == "__main__":
    unittest.main()
