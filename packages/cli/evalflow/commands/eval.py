"""Implementation of `evalflow eval`."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
import typer

from evalflow.commands._common import (
    resolve_project_path,
    exit_for_evalflow_error,
    exit_for_unexpected_error,
)
from evalflow.engine.evaluator import EvalOrchestrator
from evalflow.exceptions import ConfigError, DatasetError, EvalflowError
from evalflow.models import Dataset, EvalflowConfig, RunStatus, TestCaseResult
from evalflow.output.rich_output import (
    console,
    create_eval_progress,
    print_error,
    print_eval_header,
    print_eval_summary,
    print_test_result,
    print_warning,
)
from evalflow.storage.cache import ResponseCache
from evalflow.storage.db import EvalflowDB


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

    if debug:
        console.print("Debug mode enabled - not for production use")

    try:
        asyncio.run(
            _async_eval(
                provider=provider,
                model=model,
                dataset=dataset,
                tag=tag,
                offline=offline,
                save_baseline=save_baseline,
                concurrency=concurrency,
            )
        )
    except typer.Exit:
        raise
    except EvalflowError as exc:
        exit_for_evalflow_error(exc)
    except Exception as exc:
        exit_for_unexpected_error(exc, debug=debug)


async def _async_eval(
    *,
    provider: str | None,
    model: str | None,
    dataset: str | None,
    tag: str | None,
    offline: bool,
    save_baseline: bool,
    concurrency: int,
) -> None:
    """Load config and dataset, run the orchestrator, and render progress."""

    config = _load_config()
    load_dotenv()

    selected_provider = provider or config.eval.default_provider
    provider_settings = getattr(config.providers, selected_provider, None)
    if provider_settings is None:
        raise ConfigError(
            f"Provider '{selected_provider}' is not configured",
            fix=f"Add providers.{selected_provider} to evalflow.yaml",
        )
    if model is not None:
        provider_settings.default_model = model

    dataset_path = resolve_project_path(
        dataset or config.eval.dataset,
        allowed_suffixes={".json"},
    )
    loaded_dataset = _load_dataset(dataset_path)
    # Baselines are keyed to the exact dataset content used for this run.
    dataset_hash = sha256(loaded_dataset.model_dump_json().encode()).hexdigest()
    tags = [tag] if tag else None

    async with EvalflowDB() as db:
        baseline = await db.get_baseline(dataset_hash)
        cache = ResponseCache()
        selected_cases = loaded_dataset.test_cases
        if tags:
            selected_cases = [case for case in loaded_dataset.test_cases if tag in case.tags]
        print_eval_header(selected_provider, provider_settings.default_model, len(selected_cases))
        active_cases: dict[int, str] = {}

        with create_eval_progress() as progress:
            task_id = progress.add_task("waiting...", total=len(selected_cases))

            def _render_active_cases() -> str:
                if not active_cases:
                    return "starting..."
                ordered = [active_cases[index] for index in sorted(active_cases)]
                if len(ordered) == 1:
                    return ordered[0]
                return f"{ordered[0]} +{len(ordered) - 1} more"

            def _progress_callback(event: dict[str, object]) -> None:
                event_type = str(event["event"])
                index = int(event["index"])
                test_case_id = str(event["test_case_id"])
                if event_type == "started":
                    active_cases[index] = test_case_id
                    progress.update(task_id, description=_render_active_cases())
                    return

                active_cases.pop(index, None)
                progress.update(
                    task_id,
                    advance=1,
                    description=_render_active_cases() if active_cases else "finishing...",
                )

            orchestrator = EvalOrchestrator(
                config=config,
                db=db,
                cache=cache,
                progress_callback=_progress_callback,
            )
            run = await orchestrator.run_eval(
                dataset=loaded_dataset,
                provider_name=selected_provider,
                offline=offline,
                tags=tags,
                concurrency=concurrency,
            )

        for index, result in enumerate(run.results, start=1):
            if result.score is None and result.error:
                print_warning(result.error)
                continue
            print_test_result(result, index, len(run.results))

        should_save_baseline = save_baseline or baseline is None
        if should_save_baseline:
            await orchestrator.save_baseline(run)

        print_eval_summary(run, baseline)

    if run.status is RunStatus.pass_:
        raise typer.Exit(code=0)
    if run.status is RunStatus.fail:
        raise typer.Exit(code=1)
    raise typer.Exit(code=2)


def _load_config() -> EvalflowConfig:
    """Load and validate the project configuration file."""

    config_path = Path("evalflow.yaml")
    try:
        return EvalflowConfig.from_yaml(config_path)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError("Failed to load evalflow.yaml", fix=str(exc)) from exc


def _load_dataset(path: Path) -> Dataset:
    """Load and validate the dataset JSON file."""

    try:
        return Dataset.from_json(path)
    except DatasetError:
        raise
    except Exception as exc:
        raise DatasetError("Failed to load dataset.json", fix=str(exc)) from exc
