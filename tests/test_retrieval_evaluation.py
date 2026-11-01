"""실험 평가기의 인용 검증·캐시·분모 분리를 API 호출 없이 확인한다."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts.evaluate_retrieval import (
    build_payload, evaluate_question, run, summarize, validate_judgment,
)


def question():
    return {"id": "Q01", "doc_id": "document-a", "question": "출입구 폭은?",
            "expected_answer": "출입구 폭은 1000mm.", "required_facts": ["출입구 폭 1000mm"],
            "track": "extraction_diagnostic", "grading_note": "판정 모델에는 숨길 정보"}


def chunk(doc_id="document-a", cid="a#0001"):
    return {"chunk_id": cid, "doc_id": doc_id,
            "text": "[회사 · 비밀 제목 · p.17]\n1350kg 모델의 출입구 폭은 1000mm입니다.",
            "metadata": {"doc_id": doc_id, "location": "p.17"}}


def judgment(status="supported", quote="1350kg 모델의 출입구 폭은 1000mm입니다.", cid="a#0001"):
    return {"facts": [{"fact_index": 0, "status": status,
                       "evidence": [] if quote is None else [{"chunk_id": cid, "quote": quote}],
                       "reason": "표의 대상과 폭을 확인했습니다."}]}


class QuoteValidationTest(unittest.TestCase):
    def setUp(self):
        self.payload = build_payload(question(), [chunk()])

    def test_same_fact_with_verbatim_quote_passes(self):
        self.assertEqual(validate_judgment(self.payload, judgment())["outcome"], "pass")

    def test_only_unicode_and_whitespace_are_normalized(self):
        result = validate_judgment(self.payload, judgment(quote="１３５０kg모델의\n출입구 폭은1000mm입니다."))
        self.assertEqual(result["outcome"], "pass")
        result = validate_judgment(self.payload, judgment(quote="1350kg 모델의 출입구 폭은 1m입니다."))
        self.assertEqual(result["outcome"], "review")
        # 환산 자체는 가능하지만 '인용문'을 환산해 만들어 내면 안 된다.

    def test_fabricated_quote_cannot_pass(self):
        result = validate_judgment(self.payload, judgment(quote="출입구 폭은 2000mm입니다."))
        self.assertEqual(result["outcome"], "review")
        self.assertIn("quote_not_in_chunk", result["facts"][0]["validation_issues"])

    def test_unknown_chunk_cannot_pass(self):
        self.assertEqual(validate_judgment(self.payload, judgment(cid="not-retrieved"))["outcome"], "review")

    def test_other_document_cannot_prove_target_fact(self):
        payload = build_payload(question(), [chunk(doc_id="document-b")])
        result = validate_judgment(payload, judgment())
        self.assertIn("wrong_document", result["facts"][0]["validation_issues"])
        self.assertEqual(result["outcome"], "review")

    def test_source_header_is_not_evidence(self):
        self.assertEqual(validate_judgment(self.payload, judgment(quote="회사 · 비밀 제목"))["outcome"], "review")

    def test_missing_or_trivial_evidence_needs_review(self):
        for quote in (None, "1000mm"):
            with self.subTest(quote=quote):
                self.assertEqual(validate_judgment(self.payload, judgment(quote=quote))["outcome"], "review")

    def test_missing_and_ambiguous_facts_are_not_success(self):
        self.assertEqual(validate_judgment(self.payload, judgment("unsupported", quote=None))["outcome"], "fail")
        self.assertEqual(validate_judgment(self.payload, judgment("uncertain", quote=None))["outcome"], "review")

    def test_incomplete_duplicate_and_boolean_fact_ids_are_rejected(self):
        for answer in ({"facts": []}, {"facts": [judgment()["facts"][0]] * 2},
                       {"facts": [{**judgment()["facts"][0], "fact_index": False}]}):
            with self.assertRaises(ValueError):
                validate_judgment(self.payload, answer)

    def test_partial_support_of_multiple_facts_fails_whole_question(self):
        q = {**question(), "required_facts": ["출입구 폭 1000mm", "카 내부 1800×1600mm"]}
        answer = judgment()
        answer["facts"].append({"fact_index": 1, "status": "unsupported", "evidence": [], "reason": "카 규격 없음"})
        self.assertEqual(validate_judgment(build_payload(q, [chunk()]), answer)["outcome"], "fail")

    def test_known_error_track_and_notes_are_blinded(self):
        self.assertNotIn("track", self.payload)
        self.assertNotIn("grading_note", self.payload)
        self.assertNotIn("비밀 제목", self.payload["retrieved_chunks"][0]["text"])


class ApiAndCacheTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = Path(self.directory.name)
        self.client = MagicMock()
        self.client.chat.completions.create.return_value = SimpleNamespace(
            model="judge-snapshot", id="test-response", usage=None,
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                refusal=None, content=json.dumps(judgment())))])

    def evaluate(self, q=None, chunks=None, model="judge-model"):
        return evaluate_question(q or question(), [chunk()] if chunks is None else chunks,
                                 model, self.client, self.cache)

    def test_no_results_do_not_call_api(self):
        result = self.evaluate(chunks=[])
        self.assertEqual(result["outcome"], "fail")
        self.client.chat.completions.create.assert_not_called()

    def test_identical_input_uses_cache_and_strict_schema(self):
        self.assertFalse(self.evaluate()["cache_hit"])
        self.assertTrue(self.evaluate()["cache_hit"])
        self.client.chat.completions.create.assert_called_once()
        options = self.client.chat.completions.create.call_args.kwargs
        self.assertTrue(options["response_format"]["json_schema"]["strict"])
        self.assertFalse(options["store"])

    def test_model_prompt_reference_and_chunk_changes_invalidate_cache(self):
        self.evaluate()
        self.evaluate(model="another-model")
        with patch("scripts.evaluate_retrieval.SYSTEM_PROMPT", "new prompt"):
            self.evaluate()
        self.evaluate(q={**question(), "expected_answer": "폭 1000mm"})
        changed = chunk()
        changed["text"] += "\n새 문장입니다."
        self.evaluate(chunks=[changed])
        self.assertEqual(self.client.chat.completions.create.call_count, 5)

    def test_truncated_and_refused_results_are_not_cached(self):
        response = self.client.chat.completions.create.return_value
        for finish, refusal in (("length", None), ("stop", "refused")):
            response.choices[0].finish_reason = finish
            response.choices[0].message.refusal = refusal
            with self.assertRaises(ValueError):
                self.evaluate()
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_invalid_judgment_is_not_cached(self):
        response = self.client.chat.completions.create.return_value
        response.choices[0].message.content = '{"facts": []}'
        with self.assertRaises(ValueError):
            self.evaluate()
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_diagnostics_and_errors_do_not_inflate_comparison_success(self):
        records = [
            {"method": "vector", "track": "chunking", "outcome": "pass"},
            {"method": "vector", "track": "chunking", "outcome": "error"},
            {"method": "vector", "track": "extraction_diagnostic", "outcome": "pass"},
        ]
        result = summarize(records)["vector"]
        self.assertEqual(result["chunking"]["total"], 2)
        self.assertEqual(result["chunking"]["pass"], 1)
        self.assertEqual(result["chunking"]["error"], 1)
        self.assertEqual(result["extraction_diagnostic"]["total"], 1)

    def test_default_run_does_not_create_api_client(self):
        from core import config
        fixture = self.cache / "questions.json"
        fixture.write_text(json.dumps({"questions": [question()], "documents": [{"doc_id": "document-a"}]}), encoding="utf-8")
        args = SimpleNamespace(questions=fixture, limit=None, method="both", send_to_openai=False)
        found = {"id": 1, "employee_no": "ADM-0001", "role": "super_admin",
                 "company_id": None, "is_active": True}
        with patch.object(config, "ROOT_DIR", self.cache), \
                patch("openai.OpenAI") as factory, \
                patch("app.auth.repositories.user_repository.find_user_by_employee_no", return_value=found), \
                patch("scripts.evaluate_retrieval.source_snapshot", return_value={"chunk_count": 1}):
            result = run(args)
        self.assertEqual(result["api_calls"], 0)
        self.assertEqual(result["status"], "preflight_complete")
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
