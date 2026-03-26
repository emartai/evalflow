"""Shared command helpers for consistent error handling."""

from __future__ import annotations

from pathlib import Path

import typer

from evalflow.exceptions import ConfigError, EvalflowError
from evalflow.output.rich_output import console, print_error


def ensure_project() -> None:
    """Require the current directory to contain an evalflow project."""

    if not Path("evalflow.yaml").exists():
        raise ConfigError("Not an evalflow project", fix="Run: evalflow init")


def resolve_project_path(user_path: str, *, allowed_suffixes: set[str]) -> Path:
    """Resolve a user-supplied path relative to the current project safely."""

    base_dir = Path.cwd().resolve()
    resolved = (base_dir / user_path).resolve()
    if not str(resolved).startswith(str(base_dir)):
        raise ConfigError(
            f"Path traversal detected: {user_path}",
            fix="Use a path inside the current project directory",
        )
    if resolved.suffix.lower() not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise ConfigError(
            f"Unsupported file extension: {resolved.suffix or '(none)'}",
            fix=f"Use one of: {allowed}",
        )
    return resolved


def exit_for_evalflow_error(exc: EvalflowError) -> None:
    """Render a known evalflow error and exit consistently."""

    print_error(
        getattr(exc, "message", str(exc)),
        getattr(exc, "fix", ""),
        getattr(exc, "link", "") or None,
    )
    raise typer.Exit(code=2) from exc


def exit_for_unexpected_error(exc: Exception, *, debug: bool = False) -> None:
    """Render the final fallback unexpected-error path."""

    if debug:
        console.print_exception()
    else:
        print_error("An unexpected error occurred", "Run with --debug for details")
    raise typer.Exit(code=2) from exc
