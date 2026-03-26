"""Implementation of `evalflow prompt` commands."""

from __future__ import annotations

from pathlib import Path

import typer

from evalflow.commands._common import (
    ensure_project,
    exit_for_evalflow_error,
    exit_for_unexpected_error,
)
from evalflow.exceptions import EvalflowError
from evalflow.output.rich_output import console, print_error, print_prompt_diff, print_prompt_list
from evalflow.registry.prompt_registry import PromptRegistry

prompt_app = typer.Typer(help="Manage prompt versions")


@prompt_app.command("create")
def prompt_create(name: str = typer.Argument(..., help="Prompt name in lowercase kebab-case")) -> None:
    """Create a new prompt YAML file."""

    try:
        ensure_project()
        registry = PromptRegistry(Path("prompts"))
        prompt = registry.create_prompt(name, author="unknown")
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)

    console.print(f"Created prompts/{prompt.id}.yaml")


@prompt_app.command("list")
def prompt_list() -> None:
    """List all prompts with status."""

    try:
        ensure_project()
        registry = PromptRegistry(Path("prompts"))
        prompts = registry.list_prompts()
        print_prompt_list(prompts)
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)


@prompt_app.command("diff")
def prompt_diff(
    name: str = typer.Argument(..., help="Prompt name"),
    v1: int = typer.Argument(..., help="Older version number"),
    v2: int = typer.Argument(..., help="Newer version number"),
) -> None:
    """Show a diff between two prompt versions."""

    try:
        ensure_project()
        registry = PromptRegistry(Path("prompts"))
        diff_text = registry.diff_versions(name, v1, v2)
        versions = {
            version.version: version
            for version in registry._load_versions(registry._prompt_path(name))
        }
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)

    if not diff_text:
        console.print("No differences found.")
        return
    print_prompt_diff(versions[v1], versions[v2])


@prompt_app.command("promote")
def prompt_promote(
    name: str = typer.Argument(..., help="Prompt name"),
    to: str = typer.Option(..., "--to", help="Target status [staging|production]"),
) -> None:
    """Promote a prompt version to staging or production."""

    try:
        ensure_project()
        registry = PromptRegistry(Path("prompts"))
        if to not in {"staging", "production"}:
            print_error("Invalid target. Use: staging or production", "")
            raise typer.Exit(code=2)

        console.print("Consider running evalflow eval before promoting to production.")
        registry.promote_prompt(name, to)
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)

    console.print(f"{name} promoted to {to}")
