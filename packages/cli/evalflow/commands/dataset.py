"""Dataset validation commands."""

from __future__ import annotations

from pathlib import Path

import typer

from evalflow.commands._common import resolve_project_path
from evalflow.exceptions import DatasetError
from evalflow.models import Dataset, KEBAB_CASE_PATTERN
from evalflow.output.rich_output import console, print_doctor_check, print_error

dataset_app = typer.Typer(help="Validate datasets")


@dataset_app.command("lint")
def dataset_lint_command(
    path: str = typer.Argument("evals/dataset.json", help="Path to dataset JSON"),
) -> None:
    """Validate dataset structure and per-test-case quality checks."""

    try:
        dataset_path = resolve_project_path(path, allowed_suffixes={".json"})
        dataset = Dataset.from_json(dataset_path)
    except DatasetError as exc:
        print_error(getattr(exc, "message", str(exc)), getattr(exc, "fix", ""))
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        print_error("Failed to load dataset.json", str(exc))
        raise typer.Exit(code=2) from exc

    issue_count = 0
    print_doctor_check(f"dataset.json valid ({len(dataset.test_cases)} test cases)", True)

    for test_case in dataset.test_cases:
        checks = [
            ("id kebab-case", bool(KEBAB_CASE_PATTERN.fullmatch(test_case.id)), test_case.id),
            ("input non-empty", bool(test_case.input.strip()), test_case.id),
            (
                "expected_output reasonable length",
                len(test_case.expected_output.strip()) >= 3,
                test_case.id,
            ),
        ]
        for label, status, test_case_id in checks:
            print_doctor_check(f"{test_case_id}: {label}", status)
            if not status:
                issue_count += 1

    console.print()
    if issue_count == 0:
        console.print(f"Dataset hash: {dataset.compute_hash()}")
        console.print("Dataset lint passed.")
        raise typer.Exit(code=0)

    console.print(f"Dataset lint found {issue_count} issue(s).")
    raise typer.Exit(code=2)
