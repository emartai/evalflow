"""Core evaluation orchestration."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from time import perf_counter

from evalflow.engine.base import BaseProvider, ProviderConfig
import evalflow.engine.methods as methods_module
from evalflow.engine.providers import get_provider, resolve_provider_config
from evalflow.exceptions import DatasetError, EvalflowError, ProviderError, StorageError
from evalflow.models import (
    BaselineComparison,
    Dataset,
    EvalMethod,
    EvalRun,
    EvalflowConfig,
    RunStatus,
    TestCase,
    TestCaseResult,
)
from evalflow.storage.cache import ResponseCache
from evalflow.storage.db import EvalflowDB


UTC = timezone.utc


class EvalOrchestrator:
    """Run datasets against a provider and persist the results."""

    def __init__(
        self,
        config: EvalflowConfig,
        db: EvalflowDB,
        cache: ResponseCache,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.cache = cache
        self.progress_callback = progress_callback
        self.exact_match = methods_module.ExactMatchEvaluator()
        self.embedding = methods_module.get_embedding_evaluator()
        self.consistency = methods_module.ConsistencyEvaluator()
        self.last_baseline_comparison: BaselineComparison | None = None

    async def run_eval(
        self,
        dataset: Dataset,
        provider_name: str,
        offline: bool = False,
        tags: list[str] | None = None,
        concurrency: int = 5,
    ) -> EvalRun:
        """Run the dataset through the configured eval pipeline."""

        provider_config = resolve_provider_config(
            provider_name,
            self.config,
            allow_missing_api_key=offline,
        )
        test_cases = self._filter_test_cases(dataset, tags)
        if not test_cases:
            raise DatasetError(
                "No test cases matched the selected tags",
                fix="Remove the tag filter or add matching tags to dataset.json",
            )

        provider_class = get_provider(provider_name)
        provider = provider_class()
        started_at = datetime.now(UTC)
        started_timer = perf_counter()
        run_id = self._compute_run_id()
        dataset_hash = self._compute_dataset_hash(dataset)

        results = await self._run_test_cases(
            test_cases=test_cases,
            provider=provider,
            provider_config=provider_config,
            offline=offline,
            concurrency=concurrency,
        )

        overall_score = self._compute_overall_score(test_cases, results)
        status = self._compute_run_status(results)
        run = EvalRun(
            id=run_id,
            created_at=started_at,
            provider=provider_name,
            model=provider_config.model,
            dataset_hash=dataset_hash,
            prompt_version_hash=None,
            status=status,
            overall_score=overall_score,
            duration_ms=(perf_counter() - started_timer) * 1000.0,
            results=results,
        )
        self.last_baseline_comparison = await self.compare_to_baseline(run)
        await self.db.save_run(run)
        await self.db.save_results(run.id, results)
        return run

    async def _run_test_cases(
        self,
        *,
        test_cases: list[TestCase],
        provider: BaseProvider,
        provider_config: ProviderConfig,
        offline: bool,
        concurrency: int,
    ) -> list[TestCaseResult]:
        """Run test cases concurrently while preserving input order."""

        bounded_concurrency = max(1, concurrency)
        semaphore = asyncio.Semaphore(bounded_concurrency)
        results: list[TestCaseResult | None] = [None] * len(test_cases)

        async def _run_one(index: int, test_case: TestCase) -> tuple[int, TestCaseResult]:
            async with semaphore:
                if self.progress_callback is not None:
                    self.progress_callback(
                        {
                            "event": "started",
                            "index": index,
                            "test_case_id": test_case.id,
                        }
                    )
                started_at = perf_counter()
                result = await self._run_test_case(
                    test_case=test_case,
                    provider=provider,
                    provider_config=provider_config,
                    offline=offline,
                )

            if self.progress_callback is not None:
                self.progress_callback(
                    {
                        "event": "completed",
                        "index": index,
                        "test_case_id": test_case.id,
                        "elapsed_ms": (perf_counter() - started_at) * 1000.0,
                        "result": result,
                    }
                )
            return index, result

        tasks = [
            asyncio.create_task(_run_one(index, test_case))
            for index, test_case in enumerate(test_cases)
        ]
        completed = await asyncio.gather(*tasks)
        for index, result in completed:
            results[index] = result

        return [result for result in results if result is not None]

    async def _run_test_case(
        self,
        test_case: TestCase,
        provider: BaseProvider,
        provider_config: ProviderConfig,
        offline: bool,
    ) -> TestCaseResult:
        """Run all configured eval methods for a single test case."""

        provider_name = provider.provider_name()

        try:
            actual_output = self.cache.get(
                provider_name,
                provider_config.model,
                test_case.input,
            )

            if offline:
                if actual_output is None:
                    return self._build_result(
                        test_case_id=test_case.id,
                        status=RunStatus.pass_,
                        score=None,
                        error=f"Skipping {test_case.id} - no cached response (run online first)",
                    )

            if actual_output is None:
                response = await provider.complete(test_case.input, provider_config)
                actual_output = response.content
                self.cache.set(
                    provider_name,
                    provider_config.model,
                    test_case.input,
                    actual_output,
                )

            scores = await self._run_eval_methods(
                test_case=test_case,
                actual_output=actual_output,
                provider=provider,
                provider_config=provider_config,
                offline=offline,
            )
            score = self._compute_test_case_score(scores)
            status = (
                RunStatus.pass_
                if score >= self.config.thresholds.task_success
                else RunStatus.fail
            )
            return self._build_result(
                test_case_id=test_case.id,
                status=status,
                score=score,
                exact_match_score=scores.get("exact_match"),
                embedding_score=scores.get("embedding"),
                consistency_score=scores.get("consistency"),
                judge_score=scores.get("judge"),
                raw_output=actual_output if self.config.storage.store_raw_outputs else None,
            )
        except (ProviderError, StorageError, EvalflowError):
            raise
        except Exception as exc:
            return self._build_result(
                test_case_id=test_case.id,
                status=RunStatus.error,
                score=0.0,
                error=str(exc),
            )

    async def _run_eval_methods(
        self,
        test_case: TestCase,
        actual_output: str,
        provider: BaseProvider,
        provider_config: ProviderConfig,
        offline: bool = False,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        methods = test_case.eval_config.methods

        if EvalMethod.exact_match in methods:
            scores["exact_match"] = self.exact_match.evaluate(
                actual_output, test_case.expected_output
            )

        if EvalMethod.embedding_similarity in methods:
            scores["embedding"] = self.embedding.evaluate(
                actual_output, test_case.expected_output
            )

        if EvalMethod.consistency in methods:
            scores["consistency"] = await self.consistency.evaluate(
                prompt=test_case.input,
                provider=provider,
                provider_config=provider_config,
                runs=self.config.eval.consistency_runs,
            )

        if (test_case.eval_config.judge or EvalMethod.llm_judge in methods) and not offline:
            judge_provider_name = self.config.judge.provider
            judge_provider_class = get_provider(judge_provider_name)
            judge_provider = judge_provider_class()
            judge_config = resolve_provider_config(judge_provider_name, self.config)
            judge_config.model = self.config.judge.model
            judge = methods_module.LLMJudgeEvaluator(judge_provider, judge_config)
            judge_result = await judge.evaluate(
                input_text=test_case.input,
                expected=test_case.expected_output,
                actual=actual_output,
                context=test_case.context,
            )
            scores["judge"] = judge_result.score

        return scores

    async def compare_to_baseline(
        self, run: EvalRun
    ) -> BaselineComparison | None:
        """Compare a run against the latest stored baseline for the same dataset."""

        baseline = await self.db.get_baseline(run.dataset_hash)
        if baseline is None:
            return None

        baseline_score = float(baseline["scores"]["overall_score"])
        current_score = float(run.overall_score)
        delta = current_score - baseline_score
        return BaselineComparison(
            baseline_run_id=baseline["run_id"],
            baseline_score=baseline_score,
            current_score=current_score,
            delta=delta,
            regression=current_score < baseline_score,
        )

    @staticmethod
    def _compute_run_id() -> str:
        """Unique run ID based on current timestamp and random entropy."""

        now = datetime.now(UTC)
        entropy = secrets.token_hex(5)
        hash_suffix = sha256(f"{now.isoformat()}{entropy}".encode()).hexdigest()[:12]
        return f"{now.strftime('%Y%m%d')}-{hash_suffix}"

    async def save_baseline(self, run: EvalRun) -> None:
        """Save the run as the latest baseline."""

        await self.db.save_baseline(run)

    @staticmethod
    def _compute_dataset_hash(dataset: Dataset) -> str:
        return dataset.compute_hash()

    @staticmethod
    def _filter_test_cases(
        dataset: Dataset, tags: list[str] | None
    ) -> list[TestCase]:
        if not tags:
            return list(dataset.test_cases)
        selected_tags = set(tags)
        return [
            test_case
            for test_case in dataset.test_cases
            if selected_tags.intersection(test_case.tags)
        ]

    @staticmethod
    def _compute_test_case_score(scores: dict[str, float]) -> float:
        if not scores:
            return 0.0
        return sum(scores.values()) / len(scores)

    def _compute_overall_score(
        self, test_cases: list[TestCase], results: list[TestCaseResult]
    ) -> float:
        weighted_total = 0.0
        total_weight = 0.0
        for test_case, result in zip(test_cases, results, strict=False):
            if result.score is None:
                continue
            weight = test_case.eval_config.weight
            weighted_total += result.score * weight
            total_weight += weight
        if total_weight == 0.0:
            return 0.0
        return weighted_total / total_weight

    @staticmethod
    def _compute_run_status(results: list[TestCaseResult]) -> RunStatus:
        actionable_results = [
            result
            for result in results
            if not (
                result.score is None
                and result.error
                and result.error.startswith("Skipping ")
            )
        ]
        if any(result.status is RunStatus.error for result in actionable_results):
            return RunStatus.error
        if any(result.status is RunStatus.fail for result in actionable_results):
            return RunStatus.fail
        return RunStatus.pass_

    def _build_result(
        self,
        *,
        test_case_id: str,
        status: RunStatus,
        score: float | None,
        exact_match_score: float | None = None,
        embedding_score: float | None = None,
        consistency_score: float | None = None,
        judge_score: float | None = None,
        raw_output: str | None = None,
        error: str | None = None,
    ) -> TestCaseResult:
        return TestCaseResult.model_validate(
            {
                "test_case_id": test_case_id,
                "status": status.value,
                "score": score,
                "exact_match_score": exact_match_score,
                "embedding_score": embedding_score,
                "consistency_score": consistency_score,
                "judge_score": judge_score,
                "raw_output": raw_output,
                "error": error,
            },
            context={"max_output_chars": self.config.storage.max_output_chars},
        )
