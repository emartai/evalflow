"""Shared fixtures and bootstrap for evalflow tests."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import pytest
import yaml
from typer.testing import CliRunner

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.main import app
from evalflow.models import (
    Dataset,
    EvalCaseConfig,
    EvalMethod,
    EvalRun,
    RunStatus,
    TaskType,
    TestCase,
    TestCaseResult,
)


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Create a valid temporary evalflow project."""

    config = {
        "version": "1.0",
        "project": "test-project",
        "providers": {
            "openai": {
                "api_key_env": "OPENAI_API_KEY",
                "default_model": "gpt-4o-mini",
            }
        },
        "eval": {
            "dataset": "evals/dataset.json",
            "default_provider": "openai",
            "consistency_runs": 3,
        },
        "thresholds": {"task_success": 0.80},
    }
    dataset = {
        "version": "1.0",
        "test_cases": [
            {
                "id": "test-summarize",
                "description": "Test summarization",
                "task_type": "summarization",
                "input": "Summarize: The cat sat on the mat.",
                "expected_output": "A cat sat on a mat.",
                "context": "",
                "tags": ["smoke"],
                "eval_config": {
                    "methods": ["embedding_similarity"],
                    "judge": False,
                    "weight": 1.0,
                },
            }
        ],
    }

    (tmp_path / "evals").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / ".evalflow").mkdir()
    (tmp_path / "evalflow.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / "evals" / "dataset.json").write_text(
        json.dumps(dataset, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def mock_provider():
    """Return a provider class that yields deterministic mocked responses."""

    class MockProvider(BaseProvider):
        responses: list[str] = ["Mock response for testing."]
        call_count: int = 0
        last_prompt: str | None = None

        def __init__(self, responses: list[str] | None = None) -> None:
            if responses is not None:
                self.__class__.responses = responses
            self.__class__.call_count = 0
            self.__class__.last_prompt = None

        async def complete(
            self, prompt: str, config: ProviderConfig
        ) -> ProviderResponse:
            self.__class__.last_prompt = prompt
            response = self.responses[self.call_count % len(self.responses)]
            self.__class__.call_count += 1
            return ProviderResponse(
                content=response,
                model=config.model,
                prompt_tokens=10,
                completion_tokens=20,
                latency_ms=50.0,
            )

        async def health_check(self) -> bool:
            return True

        @classmethod
        def provider_name(cls) -> str:
            return "mock"

    return MockProvider


@pytest.fixture
def sample_dataset() -> Dataset:
    """Return a representative dataset object."""

    return Dataset(
        version="1.0",
        test_cases=[
            TestCase(
                id="test-1",
                description="Test 1",
                task_type=TaskType.summarization,
                input="Input text",
                expected_output="Expected output",
                tags=["smoke"],
                eval_config=EvalCaseConfig(
                    methods=[EvalMethod.embedding_similarity]
                ),
            )
        ],
    )


@pytest.fixture
def sample_run() -> EvalRun:
    """Return a representative eval run for output and storage tests."""

    return EvalRun(
        id="20260326-abcdef123456",
        created_at=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
        provider="openai",
        model="gpt-4o-mini",
        dataset_hash="sample-dataset-hash",
        prompt_version_hash="sample-prompt-hash",
        status=RunStatus.pass_,
        overall_score=0.92,
        duration_ms=1234.0,
        results=[
            TestCaseResult(
                test_case_id="test-1",
                status=RunStatus.pass_,
                score=0.92,
                exact_match_score=0.92,
            )
        ],
    )


runner = CliRunner()


def run_cli(
    args: list[str], *, env: dict[str, str] | None = None, input_text: str | None = None
):
    """Run a CLI command and return its Typer result."""

    return runner.invoke(
        app,
        args,
        env=env or {},
        input=input_text,
        catch_exceptions=False,
    )
