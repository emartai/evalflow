"""CLI entrypoint for evalflow."""

from __future__ import annotations

import sys

import click
import typer

from evalflow import __version__
from evalflow.exceptions import EvalflowError


_original_make_metavar = click.core.Parameter.make_metavar


def _compat_make_metavar(self: click.core.Parameter, ctx: click.Context | None = None) -> str:
    """Bridge Click/Typer metavar signature differences."""

    if ctx is None:
        fake_command = click.Command(name="evalflow")
        ctx = click.Context(fake_command)
    return _original_make_metavar(self, ctx)


click.core.Parameter.make_metavar = _compat_make_metavar


app = typer.Typer(
    name="evalflow",
    help="pytest for LLMs - catch prompt regressions before they reach production.",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
dataset_app = typer.Typer(help="Validate datasets")
prompt_app = typer.Typer(help="Manage prompt versions")
cache_app = typer.Typer(hidden=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"> evalflow v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Run the evalflow CLI."""
    del version


@app.command("init")
def init_command(
    provider: str | None = typer.Option(None, "--provider", help="LLM provider"),
    model: str | None = typer.Option(None, "--model", help="Model name"),
    non_interactive: bool = typer.Option(False, "--non-interactive", "--yes", "-y"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
    list_providers: bool = typer.Option(
        False,
        "--list-providers",
        help="Show supported providers and their default models",
    ),
) -> None:
    """Set up evalflow in your project."""

    from evalflow.commands.init import init_command as impl

    impl(
        provider=provider,
        model=model,
        non_interactive=non_interactive,
        force=force,
        list_providers=list_providers,
    )


@app.command("eval")
def eval_command(
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider: openai, anthropic, groq, gemini, or ollama",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model to use (overrides config)",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Path to dataset JSON; default: evals/dataset.json",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        "-t",
        help="Run only test cases with this tag",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use cached responses (no API calls)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show full error details",
    ),
    save_baseline: bool = typer.Option(
        False,
        "--save-baseline",
        help="Save this run as the new baseline",
    ),
    concurrency: int = typer.Option(
        5,
        "--concurrency",
        help="Maximum number of test cases to run in parallel",
        min=1,
    ),
) -> None:
    """Run the LLM quality gate against your dataset.

    Exits 0 on pass, 1 on quality failure (blocks CI), 2 on error.
    """

    from evalflow.commands.eval import eval_command as impl

    impl(
        provider=provider,
        model=model,
        dataset=dataset,
        tag=tag,
        offline=offline,
        debug=debug,
        save_baseline=save_baseline,
        concurrency=concurrency,
    )


@app.command("doctor")
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

    from evalflow.commands.doctor import doctor_command as impl

    impl(
        fix=fix,
        validate_config=validate_config,
        check_providers=check_providers,
    )


@app.command("runs")
def runs_command(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of runs to show"),
    since: str | None = typer.Option(None, "--since", help="Show runs newer than a window like 7d or 24h"),
    failed_only: bool = typer.Option(False, "--failed-only", help="Show only failed runs"),
) -> None:
    """List recent eval runs."""

    from evalflow.commands.runs import runs_command as impl

    impl(limit=limit, since=since, failed_only=failed_only)


@app.command("compare")
def compare_command(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
) -> None:
    """Compare two eval runs side by side."""

    from evalflow.commands.runs import compare_command as impl

    impl(run_a=run_a, run_b=run_b)


@dataset_app.command("lint")
def dataset_lint_command(
    path: str = typer.Argument("evals/dataset.json", help="Path to dataset JSON"),
) -> None:
    """Validate dataset structure and per-test-case quality checks."""

    from evalflow.commands.dataset import dataset_lint_command as impl

    impl(path=path)


@prompt_app.command("create")
def prompt_create(
    name: str = typer.Argument(..., help="Prompt name in lowercase kebab-case"),
    author: str = typer.Option("unknown", "--author", help="Author name to record in the prompt file"),
) -> None:
    """Create a new prompt YAML file."""

    from evalflow.commands.prompt import prompt_create as impl

    impl(name=name, author=author)


@prompt_app.command("list")
def prompt_list() -> None:
    """List all prompts with status."""

    from evalflow.commands.prompt import prompt_list as impl

    impl()


@prompt_app.command("diff")
def prompt_diff(
    name: str = typer.Argument(..., help="Prompt name"),
    v1: int = typer.Argument(..., help="Older version number"),
    v2: int = typer.Argument(..., help="Newer version number"),
) -> None:
    """Show a diff between two prompt versions."""

    from evalflow.commands.prompt import prompt_diff as impl

    impl(name=name, v1=v1, v2=v2)


@prompt_app.command("promote")
def prompt_promote(
    name: str = typer.Argument(..., help="Prompt name"),
    to: str = typer.Option(..., "--to", help="Target status [staging|production]"),
) -> None:
    """Promote a prompt version to staging or production."""

    from evalflow.commands.prompt import prompt_promote as impl

    impl(name=name, to=to)


@cache_app.command("clear")
def cache_clear_command() -> None:
    """Clear the local response cache."""

    from evalflow.commands.cache import cache_clear_command as impl

    impl()


app.add_typer(dataset_app, name="dataset")
app.add_typer(prompt_app, name="prompt")
app.add_typer(cache_app, name="cache", hidden=True)


def run() -> None:
    """Run the CLI with a global fallback error handler."""

    try:
        app()
    except EvalflowError as exc:
        from evalflow.output.rich_output import print_error

        print_error(getattr(exc, "message", str(exc)), getattr(exc, "fix", ""), getattr(exc, "link", ""))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    run()
