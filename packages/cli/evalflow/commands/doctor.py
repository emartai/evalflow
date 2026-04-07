"""Implementation of `evalflow doctor`."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import platform
import sys

import typer

from evalflow import __version__
from evalflow.commands._common import (
    ensure_project,
    exit_for_evalflow_error,
    exit_for_unexpected_error,
)
from evalflow.commands.init import GITIGNORE_ENTRIES, _add_gitignore_entries
from evalflow.engine.methods import get_embedding_evaluator
from evalflow.engine.providers import get_provider, resolve_provider_config
from evalflow.exceptions import EvalflowError
from evalflow.models import Dataset, EvalflowConfig
from evalflow.output.rich_output import console, print_doctor_check
from evalflow.storage.cache import ResponseCache
from evalflow.storage.db import EvalflowDB


def doctor_command(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix supported issues"),
    validate_config: bool = typer.Option(
        False,
        "--validate-config",
        help="Validate evalflow.yaml syntax, fields, and configured API keys",
    ),
    check_providers: bool = typer.Option(
        False,
        "--check-providers/--no-provider-check",
        help="Run live provider health checks",
    ),
) -> None:
    """Check your evalflow setup."""
    try:
        ensure_project()

        issue_count = 0
        cwd = Path.cwd()
        config_path = cwd / "evalflow.yaml"
        dataset_path = cwd / "evals" / "dataset.json"
        gitignore_path = cwd / ".gitignore"
        env_path = cwd / ".env"
        evalflow_dir = cwd / ".evalflow"

        print_doctor_check(f"evalflow {__version__} installed", True)

        python_ok = sys.version_info >= (3, 10)
        python_detail = platform.python_version()
        print_doctor_check(f"Python {python_detail}", python_ok)
        if not python_ok:
            issue_count += 1

        config = None
        config_found = config_path.exists()
        print_doctor_check("evalflow.yaml found", config_found, str(config_path) if config_found else None)
        if not config_found:
            issue_count += 1
        else:
            try:
                config = EvalflowConfig.from_yaml(config_path)
                print_doctor_check("evalflow.yaml valid", True)
            except Exception as exc:
                detail = str(exc)
                fix_detail = getattr(exc, "fix", "")
                if fix_detail:
                    detail = f"{detail} ({fix_detail})"
                print_doctor_check("evalflow.yaml valid", False, detail)
                issue_count += 1
                if validate_config:
                    console.print()
                    console.print("Config validation failed.")
                    return

        dataset_found = dataset_path.exists()
        if dataset_found:
            try:
                raw_dataset = Dataset.from_json(dataset_path)
                print_doctor_check(
                    f"dataset.json found ({len(raw_dataset.test_cases)} test cases)",
                    True,
                )
                print_doctor_check("dataset.json valid", True)
            except Exception as exc:
                print_doctor_check("dataset.json found", True, str(dataset_path))
                print_doctor_check("dataset.json valid", False, str(exc))
                issue_count += 1
        else:
            print_doctor_check("dataset.json found", False, str(dataset_path))
            issue_count += 1

        print_doctor_check(".evalflow directory exists", evalflow_dir.exists())
        if not evalflow_dir.exists():
            issue_count += 1

        db_ok = asyncio.run(_check_db(evalflow_dir / "runs.db"))
        print_doctor_check("SQLite database accessible", db_ok)
        if not db_ok:
            issue_count += 1

        cache_ok, cache_detail = _check_cache(evalflow_dir)
        print_doctor_check(f"Response cache: {cache_detail}", cache_ok)
        if not cache_ok:
            issue_count += 1

        git_ok = (cwd / ".git").exists()
        print_doctor_check("Git repository detected", git_ok)
        if not git_ok:
            if fix:
                console.print("  ! Cannot auto-fix: run [bold]git init[/bold] to initialize a repository")
            issue_count += 1

        if config is not None:
            for provider_name in _configured_providers(config):
                provider_settings = getattr(config.providers, provider_name)
                env_var = provider_settings.api_key_env
                env_set = bool(os.environ.get(env_var)) if env_var else True
                print_doctor_check(f"{env_var} set", env_set)
                if not env_set and provider_name != "ollama":
                    if fix:
                        console.print(f'  ! Cannot auto-fix: run [bold]export {env_var}="your-key-here"[/bold]')
                    issue_count += 1

                if check_providers:
                    provider_healthy = asyncio.run(_check_provider_health(provider_name, config))
                    print_doctor_check(f"{provider_name} health check", provider_healthy)
                    if not provider_healthy:
                        issue_count += 1

            if validate_config:
                console.print()
                if issue_count == 0:
                    console.print("Config validation passed.")
                else:
                    console.print("Config validation found issues.")
                return

        embedding_available = get_embedding_evaluator().is_available()
        if embedding_available:
            print_doctor_check("sentence-transformers installed", True)
        else:
            console.print("! sentence-transformers not installed (optional - needed for embedding_similarity)")
            if fix:
                console.print('  ! Cannot auto-fix: run [bold]pip install "evalflow[embeddings]"[/bold]')

        gitignore_ok = _gitignore_has_required_entries(gitignore_path)
        if not gitignore_ok and fix:
            _add_gitignore_entries(gitignore_path)
            gitignore_ok = True
        print_doctor_check(".gitignore has .env entry", gitignore_ok)
        if not gitignore_ok:
            issue_count += 1

        env_exists = env_path.exists()
        if not env_exists and fix:
            env_example = cwd / ".env.example"
            if env_example.exists():
                env_path.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
                env_exists = True
        print_doctor_check(".env file exists", env_exists)

        console.print()
        if issue_count == 0:
            console.print("Everything looks good. Run: evalflow eval")
        else:
            if fix:
                console.print(f"{issue_count} issues found. Some require manual steps (see above).")
            else:
                console.print(f"{issue_count} issues found. Run [bold]evalflow doctor --fix[/bold] to resolve what can be auto-fixed.")
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc)


async def _check_db(db_path: Path) -> bool:
    """Verify that the local SQLite database can be opened."""

    try:
        async with EvalflowDB(db_path) as db:
            await db.initialize()
        return True
    except Exception:
        return False


async def _check_provider_health(provider_name: str, config: EvalflowConfig) -> bool:
    """Run a best-effort provider health check."""

    try:
        provider_cls = get_provider(provider_name)
        provider_config = resolve_provider_config(provider_name, config)
        provider = provider_cls(health_config=provider_config)
        return await provider.health_check()
    except Exception:
        return False


def _configured_providers(config: EvalflowConfig) -> list[str]:
    """Return the configured provider names in display order."""

    return [
        name
        for name in ("openai", "anthropic", "groq", "gemini", "ollama")
        if getattr(config.providers, name) is not None
    ]


def _gitignore_has_required_entries(path: Path) -> bool:
    """Return whether the local ``.gitignore`` includes evalflow entries."""

    if not path.exists():
        return False
    lines = set(path.read_text(encoding="utf-8").splitlines())
    return all(entry in lines for entry in GITIGNORE_ENTRIES)


def _check_cache(cache_dir: Path) -> tuple[bool, str]:
    """Return cache availability plus a short human-readable summary."""

    try:
        stats = ResponseCache(cache_dir).stats()
    except Exception as exc:
        return False, str(exc)
    entries = stats["entries"]
    suffix = "entry" if entries == 1 else "entries"
    return True, f"{entries} {suffix}"
