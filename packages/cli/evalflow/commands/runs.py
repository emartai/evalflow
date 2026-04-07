"""Implementation of `evalflow runs` and `evalflow compare`."""

from __future__ import annotations

import asyncio
import re

import typer

from evalflow.commands._common import (
    ensure_project,
    exit_for_evalflow_error,
    exit_for_unexpected_error,
)
from evalflow.exceptions import ConfigError, EvalflowError
from evalflow.output.rich_output import console, print_compare_diff, print_error, print_runs_table
from evalflow.storage.db import EvalflowDB


def runs_command(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of runs to show"),
    since: str | None = typer.Option(None, "--since", help="Show runs newer than a window like 7d or 24h"),
    failed_only: bool = typer.Option(False, "--failed-only", help="Show only failed runs"),
) -> None:
    """List recent eval runs."""
    try:
        ensure_project()
        runs = asyncio.run(
            _list_runs(limit=limit, since=since, failed_only=failed_only)
        )
    except ValueError as exc:
        exit_for_evalflow_error(ConfigError("Invalid --since value", fix=str(exc)))
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)

    if not runs:
        console.print("No runs found. Run: evalflow eval")
        return

    print_runs_table(runs)


def compare_command(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
) -> None:
    """Compare two eval runs side by side."""
    try:
        ensure_project()
        left, right, results_left, results_right = asyncio.run(
            _load_compare_data(run_a, run_b)
        )
    except LookupError as exc:
        print_error(str(exc), "Run evalflow runs to see available run IDs")
        raise typer.Exit(code=2) from exc
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)

    print_compare_diff(left, right, results_left, results_right)


async def _list_runs(
    *, limit: int, since: str | None, failed_only: bool
) -> list[dict]:
    """Load filtered run history from SQLite."""

    since_days: float | None = _parse_since(since) if since else None
    async with EvalflowDB() as db:
        return await db.list_runs(limit=limit, since_days=since_days, failed_only=failed_only)


async def _load_compare_data(
    run_a: str, run_b: str
) -> tuple[dict, dict, list[dict], list[dict]]:
    """Resolve two run IDs and load their stored result rows."""

    async with EvalflowDB() as db:
        left = await _resolve_run(db, run_a)
        right = await _resolve_run(db, run_b)

        # If both partial IDs resolve to the same run, prefer the second most recent
        # distinct match for the right-hand side when possible.
        if (
            left is not None
            and right is not None
            and left["id"] == right["id"]
            and len(run_b) >= 8
        ):
            matches = await _find_matching_runs(db, run_b)
            distinct_matches = [match for match in matches if match["id"] != left["id"]]
            if distinct_matches:
                right = distinct_matches[0]

        if left is None:
            raise LookupError(f"Run ID not found: {run_a}")
        if right is None:
            raise LookupError(f"Run ID not found: {run_b}")

        results_left = await db.get_run_results(left["id"])
        results_right = await db.get_run_results(right["id"])
        return left, right, results_left, results_right


async def _resolve_run(db: EvalflowDB, value: str) -> dict | None:
    """Resolve a run by exact ID first, then by prefix when long enough."""

    run = await db.get_run(value)
    if run is not None:
        return run
    if len(value) >= 8:
        matches = await _find_matching_runs(db, value)
        return matches[0] if matches else None
    return None


async def _find_matching_runs(db: EvalflowDB, prefix: str) -> list[dict]:
    """Return recent runs whose IDs start with the given prefix."""

    runs = await db.list_runs(limit=100)
    return [run for run in runs if str(run["id"]).startswith(prefix)]


def _parse_since(value: str) -> float:
    """Convert a value like ``7d`` or ``24h`` into fractional days for filtering."""

    match = re.fullmatch(r"(\d+)([dh])", value.strip().lower())
    if match is None:
        raise ValueError("Use formats like 7d or 1h")

    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return float(amount)
    if unit == "h":
        return amount / 24.0
    raise ValueError("Use formats like 7d or 1h")
