"""CLI command tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.engine.providers import PROVIDER_REGISTRY
from evalflow.main import app
from evalflow.storage.cache import ResponseCache

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class MockProvider(BaseProvider):
    responses: list[str] = ["Expected output"]
    call_count: int = 0

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


def test_init_creates_project_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--provider", "openai", "--model", "gpt-4o-mini", "--non-interactive"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert (tmp_path / "evalflow.yaml").exists()
    assert (tmp_path / "evals" / "dataset.json").exists()
    assert (tmp_path / "prompts").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".evalflow").exists()


def test_help_works_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--help"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "pytest for LLMs" in result.output
    assert "init" in result.output
    assert "eval" in result.output
    assert "prompt" in result.output


def test_version_works_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--version"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "> evalflow v0.1.1" in result.output


def test_root_help_matches_expected_command_descriptions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--help"], catch_exceptions=False)

    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "pytest for LLMs - catch prompt regressions before they reach production." in output
    assert "init" in output and "Set up evalflow in your project." in output
    assert "eval" in output and "Run the LLM quality gate against your dataset." in output
    assert "doctor" in output and "Check your evalflow setup." in output
    assert "runs" in output and "List recent eval runs." in output
    assert "compare" in output and "Compare two eval runs side by side." in output
    assert "prompt" in output and "Manage prompt versions" in output


def test_eval_help_shows_exit_codes_and_option_descriptions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["eval", "--help"], catch_exceptions=False)

    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "Run the LLM quality gate against your dataset." in output
    assert "Exits 0 on pass, 1 on quality failure (blocks CI), 2 on error." in output
    assert "LLM provider" in output
    assert "openai" in output
    assert "anthropic" in output
    assert "gemini" in output
    assert "ollama" in output
    assert "Model to use" in output
    assert "overrides" in output
    assert "config" in output
    assert "Path to dataset JSON" in output
    assert "default:" in output
    assert "evals/dataset.json" in output
    assert "Run only test cases" in output
    assert "tag" in output
    assert "Use cached responses" in output
    assert "Maximum number of test cases" in output
    assert "to run in parallel" in output
    assert "Show full error details" in output
    assert "Save this run as the new" in output
    assert "baseline" in output


def test_init_adds_gitignore_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--provider", "openai", "--model", "gpt-4o-mini", "--non-interactive"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".evalflow/" in gitignore
    assert "!.env.example" in gitignore


def test_init_does_not_overwrite_without_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = "version: old\n"
    (tmp_path / "evalflow.yaml").write_text(original, encoding="utf-8")

    result = runner.invoke(
        app,
        ["init"],
        input="n\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert (tmp_path / "evalflow.yaml").read_text(encoding="utf-8") == original


def test_init_writes_env_var_name_not_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--provider", "openai", "--model", "gpt-4o-mini", "--non-interactive"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    config = yaml.safe_load((tmp_path / "evalflow.yaml").read_text(encoding="utf-8"))
    assert config["providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"
    assert "sk-" not in (tmp_path / "evalflow.yaml").read_text(encoding="utf-8")

    dataset = json.loads((tmp_path / "evals" / "dataset.json").read_text(encoding="utf-8"))
    assert dataset["test_cases"][0]["id"] == "example-summarization"


def test_init_non_interactive_creates_project_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--provider", "groq", "--model", "llama-3.1-8b-instant", "--non-interactive"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert (tmp_path / "evalflow.yaml").exists()
    config = yaml.safe_load((tmp_path / "evalflow.yaml").read_text(encoding="utf-8"))
    assert config["providers"]["groq"]["default_model"] == "llama-3.1-8b-instant"
    assert config["providers"]["groq"]["api_key_env"] == "GROQ_API_KEY"


def test_init_non_interactive_defaults_to_openai(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--non-interactive"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    config = yaml.safe_load((tmp_path / "evalflow.yaml").read_text(encoding="utf-8"))
    assert config["providers"]["openai"]["default_model"] == "gpt-4o-mini"
    assert config["providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"


def test_init_list_providers_prints_supported_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--list-providers"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Provider" in result.output
    assert "Default model" in result.output
    assert "openai" in result.output
    assert "gpt-4o-mini" in result.output
    assert "groq" in result.output
    assert "llama-3.1-8b-instant" in result.output
    assert not (tmp_path / "evalflow.yaml").exists()


def test_init_requires_non_interactive_without_terminal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "No terminal detected. Use: evalflow init --non-interactive" in result.output
    assert not (tmp_path / "evalflow.yaml").exists()


def _write_eval_project(tmp_path: Path) -> None:
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
    (tmp_path / ".evalflow").mkdir()
    (tmp_path / "evalflow.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (tmp_path / "evals" / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")


def test_eval_exits_0_on_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        result = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert "Quality Gate: PASS" in result.output


def test_eval_exits_1_on_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    MockProvider.responses = ["Wrong output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        result = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

    assert result.exit_code == 1
    assert "Quality Gate: FAIL" in result.output


def test_eval_exits_2_on_missing_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["eval"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "evalflow.yaml not found" in result.output
    assert "Run: evalflow init" in result.output


def test_eval_exits_2_on_missing_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)

    result = runner.invoke(app, ["eval"], env={}, catch_exceptions=False)

    assert result.exit_code == 2
    assert "Missing API key for openai" in result.output
    assert "OPENAI_API_KEY" in result.output


def test_eval_exits_2_on_invalid_yaml_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evalflow.yaml").write_text("providers:\n  openai:\n    api_key_env: OPENAI_API_KEY\n    default_model gpt-4o-mini\n", encoding="utf-8")

    result = runner.invoke(app, ["eval"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "evalflow.yaml is not valid YAML" in result.output
    assert "Check line " in result.output


def test_eval_exits_2_on_invalid_config_field(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evalflow.yaml").write_text(
        yaml.safe_dump(
            {
                "providers": {"openai": {"default_model": "gpt-4o-mini"}},
                "eval": {"default_provider": "openai"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["eval"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "evalflow.yaml invalid field: providers -> openai -> api_key_env" in result.output


def test_doctor_validate_config_reports_specific_issue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evalflow.yaml").write_text("providers:\n  openai:\n    api_key_env: OPENAI_API_KEY\n    default_model gpt-4o-mini\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--validate-config"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "evalflow.yaml valid" in result.output
    assert "evalflow.yaml is not valid YAML" in result.output
    assert "Check line " in result.output


def test_doctor_shows_checkmarks_for_valid_setup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("OPENAI_API_KEY=fake-key\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(
        ".env\n.env.local\n.env.*\n!.env.example\n.evalflow/\n*.evalflow.db\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["doctor"],
        env={"OPENAI_API_KEY": "fake-key"},
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "evalflow 0.1.1 installed" in result.output
    assert "OPENAI_API_KEY set" in result.output
    assert "Response cache:" in result.output


def test_doctor_shows_x_for_missing_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")

    result = runner.invoke(app, ["doctor"], env={}, catch_exceptions=False)

    assert result.exit_code == 0
    assert "OPENAI_API_KEY set" in result.output
    assert "issues found" in result.output


def test_doctor_fix_adds_gitignore_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        ["doctor", "--fix"],
        env={"OPENAI_API_KEY": "fake-key"},
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".evalflow/" in gitignore


def test_doctor_skips_live_provider_checks_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)

    with patch("evalflow.commands.doctor._check_provider_health") as mocked_health_check:
        result = runner.invoke(
            app,
            ["doctor"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    mocked_health_check.assert_not_called()


def test_runs_shows_helpful_message_when_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)

    result = runner.invoke(app, ["runs"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "No runs found. Run: evalflow eval" in result.output


def test_runs_lists_saved_runs_after_eval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )
        result = runner.invoke(app, ["runs"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "openai" in result.output.lower()
    assert "gpt-4o-mini" in result.output


def test_runs_failed_only_filters_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    cache = ResponseCache(tmp_path / ".evalflow")

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        MockProvider.responses = ["Expected output"]
        MockProvider.call_count = 0
        runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

        cache.clear()
        MockProvider.responses = ["Wrong output"]
        MockProvider.call_count = 0
        runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

        result = runner.invoke(app, ["runs", "--failed-only"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "FAIL" in result.output


def test_compare_supports_partial_run_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    dataset_path = tmp_path / "evals" / "dataset.json"

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        MockProvider.responses = ["Expected output"]
        MockProvider.call_count = 0
        result_a = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset["test_cases"][0]["expected_output"] = "Different output"
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

        MockProvider.responses = ["Expected output"]
        MockProvider.call_count = 0
        result_b = runner.invoke(
            app,
            ["eval"],
            env={"OPENAI_API_KEY": "fake-key"},
            catch_exceptions=False,
        )

        run_id_a = _extract_run_id(result_a.output)
        run_id_b = _extract_run_id(result_b.output)
        compare = runner.invoke(
            app,
            ["compare", run_id_a[:8], run_id_b[:8]],
            catch_exceptions=False,
        )

    assert compare.exit_code == 0
    assert run_id_a in compare.output
    assert run_id_b in compare.output


def test_prompt_create_list_promote_and_diff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    (tmp_path / "prompts").mkdir()

    created = runner.invoke(app, ["prompt", "create", "summarization"], catch_exceptions=False)
    listed = runner.invoke(app, ["prompt", "list"], catch_exceptions=False)
    promoted = runner.invoke(
        app,
        ["prompt", "promote", "summarization", "--to", "production"],
        catch_exceptions=False,
    )

    prompt_file = tmp_path / "prompts" / "summarization.yaml"
    payload = yaml.safe_load(prompt_file.read_text(encoding="utf-8"))
    payload["history"] = [
        {
            "id": "summarization",
            "version": 1,
            "status": "draft",
            "body": "Write your prompt here.",
            "author": "unknown",
            "created_at": payload["created_at"],
            "tags": [],
        }
    ]
    payload["version"] = 2
    payload["body"] = "Updated prompt body."
    prompt_file.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    diffed = runner.invoke(
        app,
        ["prompt", "diff", "summarization", "1", "2"],
        catch_exceptions=False,
    )

    assert created.exit_code == 0
    assert "Created prompts/summarization.yaml" in created.output
    assert listed.exit_code == 0
    assert "summarization" in listed.output
    assert promoted.exit_code == 0
    assert "promoted to production" in promoted.output
    assert diffed.exit_code == 0
    assert "Updated prompt body." in diffed.output


def test_cache_clear_command_works_but_is_hidden_from_help(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / ".evalflow"
    cache = ResponseCache(cache_dir)
    cache.set("openai", "gpt-4o-mini", "prompt", "response")

    help_result = runner.invoke(app, ["--help"], catch_exceptions=False)
    clear_result = runner.invoke(app, ["cache", "clear"], catch_exceptions=False)

    assert help_result.exit_code == 0
    assert "cache" not in help_result.output
    assert clear_result.exit_code == 0
    assert "Response cache cleared" in clear_result.output
    assert cache.stats()["entries"] == 0


def test_eval_offline_warns_and_skips_uncached_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    MockProvider.responses = ["Expected output"]
    MockProvider.call_count = 0

    with patch.dict(PROVIDER_REGISTRY, {"openai": MockProvider}, clear=False):
        result = runner.invoke(
            app,
            ["eval", "--offline"],
            env={},
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert "Skipping exact-match-case - no cached response" in result.output
    assert "Quality Gate: PASS" in result.output


def test_dataset_lint_passes_for_valid_dataset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)

    result = runner.invoke(app, ["dataset", "lint"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "dataset.json valid" in result.output
    assert "Dataset hash:" in result.output
    assert "Dataset lint passed." in result.output


def test_dataset_lint_reports_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "dataset.json").write_text('{"version": "1.0",\n', encoding="utf-8")

    result = runner.invoke(app, ["dataset", "lint"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "dataset.json is not valid JSON" in result.output
    assert "Syntax error at line" in result.output


def test_dataset_lint_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    traversal_path = os.path.join("..", "outside.json")
    result = runner.invoke(app, ["dataset", "lint", traversal_path], catch_exceptions=False)

    assert result.exit_code == 2
    assert "Path traversal detected" in result.output


def test_dataset_lint_reports_reasonable_length_issues(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "dataset.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "test_cases": [
                    {
                        "id": "short-output-case",
                        "description": "Too short",
                        "task_type": "qa",
                        "input": "Input",
                        "expected_output": "ok",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["dataset", "lint"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "expected_output reasonable length" in result.output
    assert "Dataset lint found 1 issue" in result.output


def test_eval_rejects_dataset_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_eval_project(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    traversal_path = os.path.join("..", "outside.json")
    result = runner.invoke(
        app,
        ["eval", "--dataset", traversal_path],
        env={"OPENAI_API_KEY": "fake-key"},
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    assert "Path traversal detected" in result.output


def _extract_run_id(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Run ID: "):
            return line.split("Run ID: ", 1)[1].strip()
    raise AssertionError("Run ID not found in output")
