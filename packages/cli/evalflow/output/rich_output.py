"""Rich-based terminal rendering for evalflow."""

from __future__ import annotations

from datetime import date, datetime
import difflib

from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from evalflow.models import EvalRun, PromptVersion, RunStatus, TestCaseResult

SUCCESS_COLOR = "green"
ERROR_COLOR = "red"
WARNING_COLOR = "yellow"
MUTED_COLOR = "bright_black"

console = Console()
_result_column_width = 0


def print_eval_header(provider: str, model: str, test_count: int) -> None:
    """Print the eval execution header."""

    global _result_column_width
    _result_column_width = 0
    console.print()
    console.print(
        f"Running {test_count} test cases against {escape(model)}...",
    )
    console.print()


def print_test_result(result: TestCaseResult, index: int, total: int) -> None:
    """Print a single aligned test result row."""

    del index, total
    global _result_column_width
    _result_column_width = max(_result_column_width, len(result.test_case_id))

    symbol = "✓" if result.status is RunStatus.pass_ else "✗"
    symbol_color = SUCCESS_COLOR if result.status is RunStatus.pass_ else ERROR_COLOR
    score = f"{(result.score or 0.0):.2f}"
    gap = " " * 4

    line = Text()
    line.append(symbol, style=symbol_color)
    line.append(" ")
    line.append(result.test_case_id.ljust(_result_column_width), style=MUTED_COLOR)
    line.append(gap)
    line.append(score.rjust(4))
    console.print(line)


def print_eval_summary(
    run: EvalRun, baseline: dict | None = None
) -> None:
    """Print the end-of-run summary block."""

    failures = sum(1 for result in run.results if result.status is not RunStatus.pass_)
    gate_text = "PASS" if run.status is RunStatus.pass_ else "FAIL"
    gate_color = SUCCESS_COLOR if run.status is RunStatus.pass_ else ERROR_COLOR

    console.print()
    console.print(Text.assemble(("Quality Gate: ", "default"), (gate_text, gate_color)))
    if baseline is None:
        console.print("Baseline: saved")
    else:
        baseline_score = float(baseline["scores"]["overall_score"])
        delta = run.overall_score - baseline_score
        delta_text = f"{delta:+.2f}"
        delta_color = (
            SUCCESS_COLOR if delta > 0 else ERROR_COLOR if delta < 0 else "default"
        )
        outcome = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
        console.print(
            Text.assemble(
                ("Δ overall: ", "default"),
                (delta_text, delta_color),
                (f" ({outcome})", "default"),
            )
        )
    console.print(f"Failures: {failures}")
    console.print(f"Run ID: {run.id}")
    console.print(f"Duration: {run.duration_ms / 1000:.1f}s")
    console.print()


def print_error(title: str, fix: str, link: str | None = None) -> None:
    """Print a formatted error message."""

    console.print(Text.assemble(("✗ ", ERROR_COLOR), (title, ERROR_COLOR)))
    console.print()
    for line in fix.splitlines():
        console.print(Text(f"  {line}"))
    if link:
        if fix:
            console.print()
        console.print(Text(f"  {link}"))


def print_info(message: str) -> None:
    """Print a neutral informational line."""

    console.print(Text(escape(message)))


def print_warning(message: str) -> None:
    """Print a formatted warning message."""

    console.print(Text.assemble(("! ", WARNING_COLOR), (escape(message), "default")))


def print_doctor_check(label: str, status: bool, detail: str | None = None) -> None:
    """Print one doctor checklist line."""

    symbol = "✓" if status else "✗"
    color = SUCCESS_COLOR if status else ERROR_COLOR
    text = f"{label}"
    if detail:
        text = f"{text} {detail}"
    console.print(Text.assemble((f"{symbol} ", color), (escape(text), "default")))


def print_runs_table(runs: list[dict]) -> None:
    """Render recent runs as a Rich table."""

    table = Table(show_header=True, header_style="bold")
    table.add_column("Run ID")
    table.add_column("Date")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Score", justify="right")
    table.add_column("Status")

    for run in runs:
        created = _format_date(run.get("created_at"))
        score = f"{float(run.get('overall_score', 0.0)):.2f}"
        status = str(run.get("status", "")).upper()
        status_style = SUCCESS_COLOR if status == "PASS" else ERROR_COLOR
        table.add_row(
            escape(str(run.get("id", ""))),
            created,
            escape(str(run.get("provider", ""))),
            escape(str(run.get("model", ""))),
            score,
            f"[{status_style}]{escape(status)}[/]",
        )

    console.print(table)


def print_compare_diff(
    run_a: dict, run_b: dict, results_a: list, results_b: list
) -> None:
    """Render a side-by-side comparison between two runs."""

    table = Table(show_header=True, header_style="bold")
    table.add_column("Test Case")
    table.add_column(str(run_a.get("id", "Run A")), no_wrap=True)
    table.add_column(str(run_b.get("id", "Run B")), no_wrap=True)
    table.add_column("Δ", justify="right")
    table.add_column("Status Change")

    by_id_a = {result["test_case_id"]: result for result in results_a}
    by_id_b = {result["test_case_id"]: result for result in results_b}

    improved = 0
    degraded = 0
    changed_statuses = 0
    for test_case_id in sorted(set(by_id_a) | set(by_id_b)):
        left = by_id_a.get(test_case_id, {})
        right = by_id_b.get(test_case_id, {})
        score_a = float(left.get("score", 0.0))
        score_b = float(right.get("score", 0.0))
        delta = score_b - score_a
        delta_color = (
            SUCCESS_COLOR if delta > 0 else ERROR_COLOR if delta < 0 else "default"
        )
        status_a = str(left.get("status", "")).upper() or "UNKNOWN"
        status_b = str(right.get("status", "")).upper() or "UNKNOWN"
        status_change = f"{status_a} -> {status_b}" if status_a != status_b else "unchanged"
        status_style = (
            SUCCESS_COLOR
            if status_a != status_b and status_b == "PASS"
            else ERROR_COLOR
            if status_a != status_b and status_b != "PASS"
            else "default"
        )
        if delta > 0:
            improved += 1
        elif delta < 0:
            degraded += 1
        if status_a != status_b:
            changed_statuses += 1
        table.add_row(
            escape(test_case_id),
            f"{score_a:.2f} ({status_a})",
            f"{score_b:.2f} ({status_b})",
            f"[{delta_color}]{delta:+.2f}[/]",
            f"[{status_style}]{escape(status_change)}[/]",
        )

    console.print(table)
    overall_a = float(run_a.get("overall_score", 0.0))
    overall_b = float(run_b.get("overall_score", 0.0))
    overall_delta = overall_b - overall_a
    winner_line = "Winner: tie"
    winner_style = "default"
    if overall_delta > 0:
        winner_line = f"Winner: {run_b.get('id', 'Run B')} ({overall_delta:+.2f} overall)"
        winner_style = SUCCESS_COLOR
    elif overall_delta < 0:
        winner_line = f"Winner: {run_a.get('id', 'Run A')} ({abs(overall_delta):.2f} overall)"
        winner_style = SUCCESS_COLOR
    console.print(
        Text.assemble(
            (winner_line, winner_style),
            (
                f"  improved: {improved}, degraded: {degraded}, status changes: {changed_statuses}",
                MUTED_COLOR,
            ),
        )
    )


def create_eval_progress() -> Progress:
    """Create the configured eval progress renderer."""

    return Progress(
        SpinnerColumn(),
        TextColumn("Running"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )


def print_prompt_list(prompts: list[PromptVersion]) -> None:
    """Print prompt versions as a table."""

    table = Table(show_header=True, header_style="bold")
    table.add_column("Prompt")
    table.add_column("Version", justify="right")
    table.add_column("Status")
    table.add_column("Author")
    table.add_column("Created")

    for prompt in prompts:
        table.add_row(
            escape(prompt.id),
            str(prompt.version),
            escape(prompt.status.value),
            escape(prompt.author),
            prompt.created_at.isoformat(),
        )

    console.print(table)


def print_prompt_diff(v1: PromptVersion, v2: PromptVersion) -> None:
    """Print a line diff between two prompt bodies."""

    diff = difflib.unified_diff(
        v1.body.splitlines(),
        v2.body.splitlines(),
        fromfile=f"{v1.id}@v{v1.version}",
        tofile=f"{v2.id}@v{v2.version}",
        lineterm="",
    )
    for line in diff:
        style = (
            SUCCESS_COLOR
            if line.startswith("+") and not line.startswith("+++")
            else ERROR_COLOR
            if line.startswith("-") and not line.startswith("---")
            else "default"
        )
        console.print(Text(escape(line), style=style))


def _format_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return escape(str(value or ""))
