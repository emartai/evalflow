"""Implementation of `evalflow init`."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import typer
import yaml
from rich.table import Table

from evalflow.output.rich_output import console, print_error
from evalflow.urls import CI_GUIDE_URL

SUPPORTED_PROVIDERS = ["openai", "anthropic", "groq", "gemini", "ollama"]
PROVIDER_DEFAULTS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.1-8b-instant",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.2",
}
PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}
GITIGNORE_ENTRIES = [
    ".env",
    ".env.local",
    ".env.*",
    "!.env.example",
    ".evalflow/",
    "*.evalflow.db",
]


def init_command(
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="LLM provider: openai, anthropic, groq, gemini, or ollama",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model name; default: provider default",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        "--yes",
        "-y",
        help="Run without prompts using defaults or provided values.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing config without asking.",
    ),
    list_providers: bool = typer.Option(
        False,
        "--list-providers",
        help="Show supported providers and their default models.",
    ),
) -> None:
    """Set up evalflow in your project.

    Use interactive prompts by default, or pass ``--non-interactive`` for CI,
    Docker, and scripted setup.
    """

    cwd = Path.cwd()
    config_path = cwd / "evalflow.yaml"
    try:
        if list_providers:
            _print_supported_providers()
            return

        if config_path.exists():
            if force or non_interactive:
                pass
            else:
                overwrite = typer.confirm("Overwrite? [y/N]", default=False)
                if not overwrite:
                    raise typer.Exit()

        if not non_interactive and not sys.stdin.isatty():
            console.print("! No terminal detected. Use: evalflow init --non-interactive")
            raise typer.Exit(code=2)

        if non_interactive:
            selected_provider = _validate_provider(provider or "openai")
            selected_model = (model or PROVIDER_DEFAULTS[selected_provider]).strip()
            env_var = PROVIDER_ENV_VARS[selected_provider]
        else:
            selected_provider = _validate_provider(provider) if provider else _prompt_provider()
            selected_model = (
                model.strip()
                if model is not None
                else typer.prompt(
                    "Choose model",
                    default=PROVIDER_DEFAULTS[selected_provider],
                    show_default=True,
                ).strip()
            )
            console.print("evalflow stores the variable name, not the key itself")
            env_var = typer.prompt(
                "API key env var name",
                default=PROVIDER_ENV_VARS[selected_provider],
                show_default=True,
            ).strip()

        _write_config(config_path, selected_provider, selected_model, env_var)
        (cwd / "prompts").mkdir(parents=True, exist_ok=True)
        _write_default_dataset(cwd / "evals" / "dataset.json")
        _add_gitignore_entries(cwd / ".gitignore")
        _create_env_example(cwd / ".env.example")
        (cwd / ".evalflow").mkdir(parents=True, exist_ok=True)

        console.print("  evalflow initialized")
        console.print()
        console.print("  Next steps:")
        console.print(f'  1. Add your API key to your environment:\n     export {env_var}="your-key-here"')
        console.print()
        console.print("  2. Run your first eval:\n     evalflow eval")
        console.print()
        console.print(
            "  3. Add to CI (GitHub Actions):\n"
            f"     {CI_GUIDE_URL}"
        )
    except typer.Exit:
        raise
    except Exception as exc:
        print_error("Failed to initialize evalflow", str(exc))
        raise typer.Exit(code=2) from exc


def _prompt_provider() -> str:
    """Prompt for a provider name and validate it."""

    provider_text = ", ".join(SUPPORTED_PROVIDERS)
    provider = typer.prompt(
        f"Choose provider [{provider_text}]",
        default="openai",
        show_default=True,
    ).strip().lower()
    return _validate_provider(provider)


def _validate_provider(provider: str) -> str:
    """Return a validated provider name."""

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    return provider


def _print_supported_providers() -> None:
    """Render the provider/default-model table."""

    table = Table(show_header=True, header_style="bold")
    table.add_column("Provider")
    table.add_column("Default model")
    for provider in SUPPORTED_PROVIDERS:
        table.add_row(provider, PROVIDER_DEFAULTS[provider])
    console.print(table)


def _write_config(path: Path, provider: str, model: str, env_var: str) -> None:
    """Write the initial ``evalflow.yaml`` file."""

    config = {
        "version": "1.0",
        "project": path.parent.name,
        "providers": {
            provider: {
                "api_key_env": env_var,
                "default_model": model,
            }
        },
        "eval": {
            "dataset": "evals/dataset.json",
            "baseline_file": ".evalflow/baseline.json",
            "default_provider": provider,
            "consistency_runs": 3,
        },
        "thresholds": {
            "task_success": 0.80,
            "relevance": 0.75,
            "hallucination_max": 0.10,
            "consistency_min": 0.85,
        },
        "judge": {
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
        },
        "prompts": {"directory": "prompts/"},
        "storage": {"store_raw_outputs": True, "max_output_chars": 2000},
    }
    path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )


def _write_default_dataset(path: Path) -> None:
    """Write the starter dataset used by first-run examples."""

    path.parent.mkdir(parents=True, exist_ok=True)
    dataset = {
        "version": "1.0",
        "test_cases": [
            {
                "id": "example-greeting",
                "description": "Simple greeting test — replace with your own cases",
                "task_type": "qa",
                "input": "Reply with exactly the word: hello",
                "expected_output": "hello",
                "context": "",
                "tags": ["example"],
                "eval_config": {
                    "methods": ["exact_match"],
                    "judge": False,
                    "weight": 1.0,
                },
            }
        ],
    }
    path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")


def _add_gitignore_entries(path: Path) -> None:
    """Ensure evalflow's required ignore entries are present."""

    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    merged = list(existing_lines)
    for entry in GITIGNORE_ENTRIES:
        if entry not in merged:
            merged.append(entry)

    content = "\n".join(merged).rstrip() + "\n"
    path.write_text(content, encoding="utf-8")


def _create_env_example(path: Path) -> None:
    """Create a sample environment file if one does not exist."""

    if path.exists():
        return

    content = (
        "# evalflow environment variables\n"
        "# Copy to .env and fill in real values. Never commit .env to git.\n\n"
        "OPENAI_API_KEY=sk-your-key-here\n"
        "# ANTHROPIC_API_KEY=your-key-here\n"
        "# GROQ_API_KEY=your-key-here\n"
    )
    path.write_text(content, encoding="utf-8")
