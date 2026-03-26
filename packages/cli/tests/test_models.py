"""Model validation tests for evalflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evalflow.exceptions import ConfigError
from evalflow.exceptions import DatasetError
from evalflow.models import (
    Dataset,
    EvalRun,
    EvalflowConfig,
    PromptStatus,
    PromptVersion,
    RunStatus,
    TestCaseResult as RunTestCaseResult,
)


def write_text(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestEvalflowConfig:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "evalflow.yaml",
            """
version: "1.0"
project: demo
providers:
  openai:
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4o-mini
eval:
  dataset: evals/dataset.json
  default_provider: openai
            """.strip(),
        )

        config = EvalflowConfig.from_yaml(path)

        assert config.project == "demo"
        assert config.providers.openai is not None
        assert config.providers.openai.api_key_env == "OPENAI_API_KEY"
        assert config.storage.max_output_chars == 2000

    def test_from_yaml_rejects_non_mapping(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "evalflow.yaml", "- not\n- a\n- mapping\n")

        with pytest.raises(ConfigError, match="top level"):
            EvalflowConfig.from_yaml(path)

    def test_from_yaml_missing_file_has_helpful_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="evalflow.yaml not found"):
            EvalflowConfig.from_yaml(tmp_path / "missing.yaml")

    def test_from_yaml_requires_yaml_extension(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "evalflow.txt", "{}")

        with pytest.raises(ConfigError, match=".yaml or .yml extension"):
            EvalflowConfig.from_yaml(path)

    def test_from_yaml_rejects_empty_file(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "evalflow.yaml", "")

        with pytest.raises(ConfigError, match="evalflow.yaml is empty"):
            EvalflowConfig.from_yaml(path)

    def test_from_yaml_rejects_invalid_yaml_with_line_number(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "evalflow.yaml",
            "providers:\n  openai:\n    api_key_env: OPENAI_API_KEY\n    default_model gpt-4o-mini\n",
        )

        with pytest.raises(ConfigError, match="not valid YAML") as exc_info:
            EvalflowConfig.from_yaml(path)

        assert "Check line " in exc_info.value.fix

    def test_from_yaml_rejects_missing_required_field(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "evalflow.yaml",
            """
providers:
  openai:
    default_model: gpt-4o-mini
eval:
  default_provider: openai
            """.strip(),
        )

        with pytest.raises(ConfigError, match="providers -> openai -> api_key_env"):
            EvalflowConfig.from_yaml(path)

    def test_from_yaml_rejects_invalid_field_value(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "evalflow.yaml",
            """
providers:
  openai:
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4o-mini
eval:
  default_provider: openai
thresholds:
  task_success: 1.5
            """.strip(),
        )

        with pytest.raises(ConfigError, match="thresholds -> task_success"):
            EvalflowConfig.from_yaml(path)

    def test_default_provider_must_exist_when_providers_defined(self) -> None:
        with pytest.raises(ValidationError, match="default_provider"):
            EvalflowConfig.model_validate(
                {
                    "providers": {
                        "groq": {
                            "api_key_env": "GROQ_API_KEY",
                            "default_model": "llama-3.1-8b-instant",
                        }
                    },
                    "eval": {"default_provider": "openai"},
                }
            )

    def test_thresholds_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError):
            EvalflowConfig.model_validate({"thresholds": {"task_success": 1.5}})


class TestDataset:
    def test_load_valid_json(self, tmp_path: Path) -> None:
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "summary-check",
                            "description": "Checks summary quality",
                            "task_type": "summarization",
                            "input": "Input",
                            "expected_output": "Expected",
                            "tags": ["critical"],
                            "eval_config": {
                                "methods": ["embedding_similarity", "exact_match"],
                                "judge": False,
                                "weight": 1.0,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        dataset = Dataset.from_json(dataset_path)

        assert dataset.version == "1.0"
        assert dataset.test_cases[0].id == "summary-check"

    def test_from_json_missing_file_has_helpful_error(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="Dataset not found"):
            Dataset.from_json(tmp_path / "missing.json")

    def test_from_json_requires_json_extension(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "dataset.txt", "{}")

        with pytest.raises(DatasetError, match=".json file extension"):
            Dataset.from_json(path)

    def test_from_json_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "dataset.json", '{"version": "1.0",\n')

        with pytest.raises(DatasetError, match="not valid JSON") as exc_info:
            Dataset.from_json(path)

        assert "Syntax error at line" in exc_info.value.fix

    def test_from_json_requires_version(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "dataset.json", json.dumps({"test_cases": []}))

        with pytest.raises(DatasetError, match="Missing 'version' field"):
            Dataset.from_json(path)

    def test_from_json_requires_test_cases(self, tmp_path: Path) -> None:
        path = write_text(tmp_path / "dataset.json", json.dumps({"version": "1.0", "test_cases": []}))

        with pytest.raises(DatasetError, match="No test cases found"):
            Dataset.from_json(path)

    def test_from_json_rejects_duplicate_ids_with_helpful_error(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "dataset.json",
            json.dumps(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "dup-id",
                            "description": "First",
                            "task_type": "qa",
                            "input": "Input",
                            "expected_output": "Expected",
                        },
                        {
                            "id": "dup-id",
                            "description": "Second",
                            "task_type": "qa",
                            "input": "Input",
                            "expected_output": "Expected",
                        },
                    ],
                }
            ),
        )

        with pytest.raises(DatasetError, match="Duplicate test case IDs"):
            Dataset.from_json(path)

    def test_from_json_requires_input_and_expected_output(self, tmp_path: Path) -> None:
        path = write_text(
            tmp_path / "dataset.json",
            json.dumps(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "missing-fields",
                            "description": "Bad case",
                            "task_type": "qa",
                            "input": "",
                            "expected_output": "",
                        }
                    ],
                }
            ),
        )

        with pytest.raises(DatasetError, match="missing 'input' field"):
            Dataset.from_json(path)

    def test_rejects_non_kebab_case_id(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            Dataset.model_validate(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "Not_Kebab",
                            "description": "Bad id",
                            "task_type": "qa",
                            "input": "Input",
                            "expected_output": "Expected",
                        }
                    ],
                }
            )

    def test_rejects_duplicate_ids(self) -> None:
        payload = {
            "version": "1.0",
            "test_cases": [
                {
                    "id": "dup-id",
                    "description": "First",
                    "task_type": "qa",
                    "input": "Input",
                    "expected_output": "Expected",
                },
                {
                    "id": "dup-id",
                    "description": "Second",
                    "task_type": "qa",
                    "input": "Input",
                    "expected_output": "Expected",
                },
            ],
        }

        with pytest.raises(ValidationError, match="duplicate test case ids"):
            Dataset.model_validate(payload)

    def test_rejects_duplicate_eval_methods(self) -> None:
        with pytest.raises(ValidationError, match="must be unique"):
            Dataset.model_validate(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "unique-id",
                            "description": "Duplicate methods",
                            "task_type": "qa",
                            "input": "Input",
                            "expected_output": "Expected",
                            "eval_config": {
                                "methods": ["exact_match", "exact_match"]
                            },
                        }
                    ],
                }
            )

    def test_compute_hash_is_deterministic(self, tmp_path: Path) -> None:
        dataset_path = write_text(
            tmp_path / "dataset.json",
            json.dumps(
                {
                    "version": "1.0",
                    "test_cases": [
                        {
                            "id": "summary-check",
                            "description": "Checks summary quality",
                            "task_type": "summarization",
                            "input": "Input",
                            "expected_output": "Expected",
                        }
                    ],
                }
            ),
        )

        dataset_a = Dataset.from_json(dataset_path)
        dataset_b = Dataset.from_json(dataset_path)

        assert dataset_a.compute_hash() == dataset_b.compute_hash()


class TestPromptVersion:
    def test_status_values(self) -> None:
        prompt = PromptVersion.model_validate(
            {
                "id": "summarization",
                "version": 2,
                "status": "production",
                "body": "Prompt body",
                "author": "emmanuel",
                "created_at": "2024-03-01",
                "tags": ["core"],
            }
        )

        assert prompt.status is PromptStatus.production

    def test_version_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            PromptVersion.model_validate(
                {
                    "id": "summarization",
                    "version": 0,
                    "status": "draft",
                    "body": "Prompt body",
                    "author": "emmanuel",
                    "created_at": "2024-03-01",
                }
            )


class TestRunModels:
    def test_scores_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError, match="between 0 and 1"):
            RunTestCaseResult.model_validate(
                {
                    "test_case_id": "summary-check",
                    "status": "pass",
                    "score": 1.2,
                }
            )

    def test_raw_output_truncates_with_context(self) -> None:
        result = RunTestCaseResult.model_validate(
            {
                "test_case_id": "summary-check",
                "status": "fail",
                "score": 0.4,
                "raw_output": "abcdefghij",
            },
            context={"max_output_chars": 5},
        )

        assert result.raw_output == "abcde"

    def test_eval_run_model_creation(self) -> None:
        run = EvalRun.model_validate(
            {
                "id": "20260325-abcdef123456",
                "created_at": "2026-03-25T12:00:00",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "dataset_hash": "abc123",
                "prompt_version_hash": "def456",
                "status": "pass",
                "overall_score": 0.91,
                "duration_ms": 320.5,
                "results": [
                    {
                        "test_case_id": "summary-check",
                        "status": "pass",
                        "score": 0.91,
                    }
                ],
            }
        )

        assert run.status is RunStatus.pass_
        assert run.results[0].status is RunStatus.pass_
