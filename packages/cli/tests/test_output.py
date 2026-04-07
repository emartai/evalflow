"""Output rendering tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

from rich.console import Console

from evalflow.models import EvalRun, PromptVersion, TestCaseResult as RunTestCaseResult
from evalflow.output import rich_output


UTC = timezone.utc


def _capture_output(func) -> str:
    buffer = Console(record=True, width=120)
    original_console = rich_output.console
    rich_output.console = buffer
    try:
        func()
        return buffer.export_text()
    finally:
        rich_output.console = original_console


def make_result(test_case_id: str, status: str, score: float) -> RunTestCaseResult:
    return RunTestCaseResult.model_validate(
        {
            "test_case_id": test_case_id,
            "status": status,
            "score": score,
        }
    )


def make_run(status: str = "pass") -> EvalRun:
    return EvalRun.model_validate(
        {
            "id": "20260325-abcdef123456",
            "created_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
            "provider": "openai",
            "model": "gpt-4o-mini",
            "dataset_hash": "hash",
            "status": status,
            "overall_score": 0.91 if status == "pass" else 0.61,
            "duration_ms": 4200.0,
            "results": [
                {
                    "test_case_id": "critical-match",
                    "status": status,
                    "score": 0.91 if status == "pass" else 0.61,
                }
            ],
        }
    )


def test_print_eval_header() -> None:
    output = _capture_output(
        lambda: rich_output.print_eval_header("openai", "gpt-4o-mini", 5)
    )
    assert "Running 5 test cases against gpt-4o-mini..." in output


def test_print_test_result_formats_score() -> None:
    result = make_result("critical-match", "pass", 0.91)
    output = _capture_output(lambda: rich_output.print_test_result(result, 1, 2))
    assert "critical-match" in output
    assert "0.91" in output


def test_print_eval_summary_with_baseline_delta() -> None:
    run = make_run("pass")
    baseline = {"scores": {"overall_score": 0.80}}
    output = _capture_output(lambda: rich_output.print_eval_summary(run, baseline))
    assert "Quality Gate: PASS" in output
    assert "Δ overall: +0.11" in output or "Delta overall: +0.11" in output
    assert "Duration: 4.2s" in output


def test_print_error_escapes_markup() -> None:
    output = _capture_output(
        lambda: rich_output.print_error(
            "Bad [title]",
            "Fix [this]",
            "https://example.com/?a=[b]",
        )
    )
    assert "Bad [title]" in output
    assert "Fix [this]" in output
    assert "https://example.com/?a=[b]" in output


def test_print_runs_table() -> None:
    output = _capture_output(
        lambda: rich_output.print_runs_table(
            [
                {
                    "id": "20260325-abcdef123456",
                    "created_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "overall_score": 0.88,
                    "status": "pass",
                }
            ]
        )
    )
    assert "Run ID" in output
    assert "20260325-abcdef123456" in output
    assert "0.88" in output


def test_print_prompt_list_and_diff() -> None:
    prompt_v1 = PromptVersion.model_validate(
        {
            "id": "summarization",
            "version": 1,
            "status": "draft",
            "body": "Line one\nLine two",
            "author": "emmanuel",
            "created_at": date(2024, 3, 1),
        }
    )
    prompt_v2 = PromptVersion.model_validate(
        {
            "id": "summarization",
            "version": 2,
            "status": "production",
            "body": "Line one\nLine three",
            "author": "emmanuel",
            "created_at": date(2024, 3, 2),
        }
    )

    list_output = _capture_output(
        lambda: rich_output.print_prompt_list([prompt_v1, prompt_v2])
    )
    diff_output = _capture_output(lambda: rich_output.print_prompt_diff(prompt_v1, prompt_v2))

    assert "summarization" in list_output
    assert "production" in list_output
    assert "@@ " not in diff_output or "Line three" in diff_output
    assert "Line three" in diff_output


def test_print_compare_diff_shows_status_changes_and_winner() -> None:
    output = _capture_output(
        lambda: rich_output.print_compare_diff(
            {
                "id": "20260325-left",
                "overall_score": 0.50,
            },
            {
                "id": "20260325-right",
                "overall_score": 0.90,
            },
            [{"test_case_id": "critical-match", "score": 0.50, "status": "fail"}],
            [{"test_case_id": "critical-match", "score": 0.90, "status": "pass"}],
        )
    )
    assert "PASS -> FAIL" not in output
    assert "FAIL -> PASS" in output
    assert "Winner: 20260325-right" in output
