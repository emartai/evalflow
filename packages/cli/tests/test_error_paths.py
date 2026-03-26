"""Dedicated integration tests for command error paths."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.engine.providers import PROVIDER_REGISTRY
from evalflow.exceptions import ProviderError
from evalflow.main import app

runner = CliRunner()


def _write_project(tmp_path: Path) -> None:
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
        "thresholds": {
            "task_success": 0.80,
            "relevance": 0.75,
            "hallucination_max": 0.10,
            "consistency_min": 0.85,
        },
        "judge": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "prompts": {"directory": "prompts/"},
        "storage": {"store_raw_outputs": True, "max_output_chars": 2000},
    }
    dataset = {
        "version": "1.0",
        "test_cases": [
            {
                "id": "exact-match-case",
                "description": "Exact match",
                "task_type": "qa",
                "input": "Input",
                "expected_output": "Expected output",
                "tags": ["critical"],
                "eval_config": {"methods": ["exact_match"], "judge": False, "weight": 1.0},
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
        json.dumps(dataset),
        encoding="utf-8",
    )


class AuthFailProvider(BaseProvider):
    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        raise ProviderError("openai", "OpenAI API request failed: 401", 401)

    async def health_check(self) -> bool:
        return True

    @classmethod
    def provider_name(cls) -> str:
        return "openai"


class OfflineProvider(BaseProvider):
    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        raise ProviderError("openai", "OpenAI request failed due to a connection problem")

    async def health_check(self) -> bool:
        return True

    @classmethod
    def provider_name(cls) -> str:
        return "openai"


def test_eval_missing_project_shows_init_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["eval"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "evalflow.yaml not found" in result.output
    assert "Run: evalflow init" in result.output
    assert "Traceback" not in result.output


def test_runs_without_project_shows_not_an_evalflow_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["runs"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "Not an evalflow project" in result.output
    assert "Run: evalflow init" in result.output
    assert "Traceback" not in result.output


def test_doctor_without_project_shows_not_an_evalflow_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "Not an evalflow project" in result.output
    assert "Run: evalflow init" in result.output
    assert "Traceback" not in result.output


def test_prompt_list_without_project_shows_not_an_evalflow_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["prompt", "list"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "Not an evalflow project" in result.output
    assert "Run: evalflow init" in result.output
    assert "Traceback" not in result.output


def test_eval_with_provider_auth_failure_shows_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    with patch.dict(PROVIDER_REGISTRY, {"openai": AuthFailProvider}, clear=False):
        result = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "bad-key"},
            catch_exceptions=False,
        )

    assert result.exit_code == 2
    assert "OpenAI API request failed: 401" in result.output
    assert "Check your OPENAI API key and provider configuration" in result.output
    assert "Traceback" not in result.output


def test_eval_with_invalid_dataset_json_shows_location(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)
    (tmp_path / "evals" / "dataset.json").write_text('{"version": "1.0",\n', encoding="utf-8")

    result = runner.invoke(
        app,
        ["eval"],
        env={"OPENAI_API_KEY": "fake-key"},
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    assert "dataset.json is not valid JSON" in result.output
    assert "Syntax error at line" in result.output
    assert "Traceback" not in result.output


def test_eval_with_connection_problem_shows_offline_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    with patch.dict(PROVIDER_REGISTRY, {"openai": OfflineProvider}, clear=False):
        result = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

    assert result.exit_code == 2
    assert "OpenAI request failed due to a connection problem" in result.output
    assert "Check your internet connection or provider availability" in result.output
    assert "Traceback" not in result.output


def test_compare_invalid_run_ids_shows_lookup_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = runner.invoke(
        app,
        ["compare", "xyz", "abc"],
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    assert "Run ID not found: xyz" in result.output
    assert "Run evalflow runs to see available run IDs" in result.output
    assert "Traceback" not in result.output


def test_prompt_promote_invalid_target_shows_expected_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)
    (tmp_path / "prompts" / "summarization.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "summarization",
                "version": 1,
                "status": "draft",
                "body": "Write your prompt here.",
                "author": "unknown",
                "created_at": "2026-03-26",
                "tags": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["prompt", "promote", "summarization", "--to", "invalid"],
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    assert "Invalid target. Use: staging or production" in result.output
    assert "Traceback" not in result.output
