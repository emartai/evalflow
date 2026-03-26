"""Integration tests for the eval orchestrator."""

from __future__ import annotations

import os
import re
import asyncio
from unittest.mock import patch

import pytest

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.engine.evaluator import EvalOrchestrator
from evalflow.engine.providers import PROVIDER_REGISTRY
from evalflow.models import Dataset, EvalMethod, EvalflowConfig
from evalflow.storage.cache import ResponseCache
from evalflow.storage.db import EvalflowDB


class MockProvider(BaseProvider):
    responses: list[str] = ["Expected output"]
    call_count: int = 0

    def __init__(self) -> None:
        pass

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        response = self.responses[self.call_count % len(self.responses)]
        self.__class__.call_count += 1
        return ProviderResponse(
            content=response,
            model=config.model,
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1.0,
        )

    async def health_check(self) -> bool:
        return True

    @classmethod
    def provider_name(cls) -> str:
        return "openai"


class DelayedProvider(BaseProvider):
    call_count: int = 0

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        self.__class__.call_count += 1
        if prompt.endswith("A"):
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.01)
        return ProviderResponse(
            content="Expected output",
            model=config.model,
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1.0,
        )

    async def health_check(self) -> bool:
        return True

    @classmethod
    def provider_name(cls) -> str:
        return "openai"


def make_config() -> EvalflowConfig:
    return EvalflowConfig.model_validate(
        {
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
            "thresholds": {"task_success": 0.8},
        }
    )


def make_dataset() -> Dataset:
    return Dataset.model_validate(
        {
            "version": "1.0",
            "test_cases": [
                {
                    "id": "critical-match",
                    "description": "Critical case",
                    "task_type": "qa",
                    "input": "Input A",
                    "expected_output": "Expected output",
                    "tags": ["critical"],
                    "eval_config": {"methods": ["exact_match"], "weight": 1.0},
                },
                {
                    "id": "optional-match",
                    "description": "Optional case",
                    "task_type": "qa",
                    "input": "Input B",
                    "expected_output": "Expected output",
                    "tags": ["optional"],
                    "eval_config": {"methods": ["exact_match"], "weight": 2.0},
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_run_id_format_and_determinism(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(config, db, cache)
                first = await orchestrator.run_eval(dataset, "openai")
                second_id = orchestrator._compute_run_id(dataset, "openai", "gpt-4o-mini")

    assert re.fullmatch(r"\d{8}-[a-f0-9]{12}", first.id)
    assert first.id == second_id


@pytest.mark.asyncio
async def test_baseline_comparison_logic(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                MockProvider.responses = ["Expected output"]
                MockProvider.call_count = 0
                orchestrator = EvalOrchestrator(config, db, cache)
                baseline_run = await orchestrator.run_eval(dataset, "openai")
                await orchestrator.save_baseline(baseline_run)

                cache.clear()
                MockProvider.responses = ["wrong output"]
                MockProvider.call_count = 0
                degraded_run = await orchestrator.run_eval(dataset, "openai")
                comparison = orchestrator.last_baseline_comparison

    assert comparison is not None
    assert comparison.baseline_run_id == baseline_run.id
    assert comparison.current_score < comparison.baseline_score
    assert comparison.regression is True
    assert degraded_run.status.value in {"fail", "error"}


@pytest.mark.asyncio
async def test_tag_filtering(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(config, db, cache)
                run = await orchestrator.run_eval(dataset, "openai", tags=["critical"])

    assert len(run.results) == 1
    assert run.results[0].test_case_id == "critical-match"


@pytest.mark.asyncio
async def test_offline_mode_uses_cache(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(config, db, cache)
                await orchestrator.run_eval(dataset, "openai")
                online_calls = MockProvider.call_count
                offline_run = await orchestrator.run_eval(dataset, "openai", offline=True)

    assert MockProvider.call_count == online_calls
    assert all(result.error is None for result in offline_run.results)


@pytest.mark.asyncio
async def test_online_mode_reuses_cache_before_calling_provider(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(config, db, cache)
                await orchestrator.run_eval(dataset, "openai")
                first_call_count = MockProvider.call_count
                second_run = await orchestrator.run_eval(dataset, "openai")

    assert MockProvider.call_count == first_call_count
    assert all(result.error is None for result in second_run.results)


@pytest.mark.asyncio
async def test_offline_mode_skips_uncached_cases_without_provider_calls(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(config, db, cache)
                run = await orchestrator.run_eval(dataset, "openai", offline=True)

    assert MockProvider.call_count == 0
    assert all(result.score is None for result in run.results)
    assert all("Skipping " in (result.error or "") for result in run.results)
    assert run.status.value == "pass"


@pytest.mark.asyncio
async def test_run_eval_limits_concurrency_and_preserves_input_order(tmp_path) -> None:
    config = make_config()
    dataset = make_dataset()
    cache = ResponseCache(tmp_path / ".evalflow")
    DelayedProvider.call_count = 0
    active = 0
    max_active = 0
    completed_indices: list[int] = []

    def progress_callback(event: dict[str, object]) -> None:
        nonlocal active, max_active
        if event["event"] == "started":
            active += 1
            max_active = max(max_active, active)
            return
        active -= 1
        completed_indices.append(int(event["index"]))

    with patch.dict(PROVIDER_REGISTRY, {"openai": DelayedProvider}, clear=False):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}, clear=False):
            async with EvalflowDB(tmp_path / ".evalflow" / "runs.db") as db:
                orchestrator = EvalOrchestrator(
                    config,
                    db,
                    cache,
                    progress_callback=progress_callback,
                )
                run = await orchestrator.run_eval(dataset, "openai", concurrency=2)

    assert max_active <= 2
    assert completed_indices == [1, 0]
    assert [result.test_case_id for result in run.results] == [
        "critical-match",
        "optional-match",
    ]
