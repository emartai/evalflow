"""Hidden cache maintenance commands."""

from __future__ import annotations

from pathlib import Path

import typer

from evalflow.output.rich_output import console, print_error
from evalflow.storage.cache import ResponseCache

cache_app = typer.Typer(hidden=True)


@cache_app.command("clear")
def cache_clear_command() -> None:
    """Clear the local response cache."""

    try:
        cache = ResponseCache(Path(".evalflow"))
        cache.clear()
        console.print("✓ Response cache cleared")
    except Exception as exc:
        print_error("Failed to clear response cache", str(exc))
        raise typer.Exit(code=2) from exc
