import asyncio
import json
import math
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evals.run_ragas import _score_samples, _validate_local_database_url


class _FakeMetric:
    def __init__(self, value):
        self.value = value
        self.inputs = []

    async def ascore(self, **kwargs):
        self.inputs.append(kwargs)
        return SimpleNamespace(value=self.value)


class RagEvaluationDatasetTests(unittest.TestCase):
    def test_golden_dataset_has_twenty_to_thirty_complete_cases(self):
        dataset_path = (
            Path(__file__).resolve().parents[1]
            / "evals"
            / "data"
            / "questions.json"
        )
        cases = json.loads(dataset_path.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(cases), 20)
        self.assertLessEqual(len(cases), 30)
        for case in cases:
            self.assertTrue(case["user_input"].strip())
            self.assertTrue(case["reference"].strip())

    def test_evaluation_requires_a_local_database(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost:5433/project_manager"},
        ):
            _validate_local_database_url()

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@database.example/project_manager"},
        ):
            with self.assertRaisesRegex(RuntimeError, "remote database hosts"):
                _validate_local_database_url()

    def test_evaluation_requires_database_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "Set DATABASE_URL"):
                _validate_local_database_url()

    def test_scoring_runs_both_metrics_and_preserves_sample_fields(self):
        sample = {
            "user_input": "Which database?",
            "response": "PostgreSQL.",
            "reference": "PostgreSQL.",
            "retrieved_contexts": ["The database is PostgreSQL."],
        }
        faithfulness = _FakeMetric(0.9)
        answer_relevancy = _FakeMetric(0.8)

        scores = asyncio.run(
            _score_samples([sample], faithfulness, answer_relevancy)
        )

        self.assertEqual(scores[0]["faithfulness"], 0.9)
        self.assertEqual(scores[0]["answer_relevancy"], 0.8)
        self.assertEqual(scores[0]["reference"], sample["reference"])
        self.assertEqual(
            faithfulness.inputs[0]["retrieved_contexts"],
            sample["retrieved_contexts"],
        )
        self.assertNotIn("retrieved_contexts", answer_relevancy.inputs[0])

    def test_scoring_rejects_non_finite_metric_results(self):
        sample = {
            "user_input": "Which database?",
            "response": "PostgreSQL.",
            "retrieved_contexts": ["The database is PostgreSQL."],
        }

        with self.assertRaisesRegex(RuntimeError, "non-finite score"):
            asyncio.run(
                _score_samples(
                    [sample],
                    _FakeMetric(math.nan),
                    _FakeMetric(0.8),
                )
            )


if __name__ == "__main__":
    unittest.main()
