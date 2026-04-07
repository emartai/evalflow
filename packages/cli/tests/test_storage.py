"""Storage tests for evalflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os

import pytest

from evalflow.models import EvalRun, RunStatus
from evalflow.models import TestCaseResult as RunTestCaseResult
from evalflow.storage.cache import ResponseCache
from evalflow.storage.db import EvalflowDB


UTC = timezone.utc


def make_result(
    test_case_id: str,
    status: str = "pass",
    score: float = 0.9,
    raw_output: str | None = "cached output",
) -> RunTestCaseResult:
    return RunTestCaseResult.model_validate(
        {
            "test_case_id": test_case_id,
            "status": status,
            "score": score,
            "exact_match_score": score,
            "embedding_score": score,
            "consistency_score": score,
            "judge_score": score,
            "raw_output": raw_output,
            "error": None,
        }
    )


def make_run(
    run_id: str = "20260325-abcdef123456",
    *,
    created_at: datetime | None = None,
    status: str = "pass",
    dataset_hash: str = "dataset-hash",
    overall_score: float = 0.9,
) -> EvalRun:
    return EvalRun.model_validate(
        {
            "id": run_id,
            "created_at": created_at or datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
            "provider": "openai",
            "model": "gpt-4o-mini",
            "dataset_hash": dataset_hash,
            "prompt_version_hash": "prompt-hash",
            "status": status,
            "overall_score": overall_score,
            "duration_ms": 150.0,
            "results": [make_result("test-case-1", status=status, score=overall_score)],
        }
    )


class TestEvalflowDB:
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"

        async with EvalflowDB(db_path) as db:
            await db.initialize()

        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_save_and_retrieve_run(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        run = make_run()

        async with EvalflowDB(db_path) as db:
            await db.save_run(run)

            saved = await db.get_run(run.id)

        assert saved is not None
        assert saved["id"] == run.id
        assert saved["status"] == RunStatus.pass_.value

    @pytest.mark.asyncio
    async def test_save_and_retrieve_results(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        run = make_run()
        results = [
            make_result("test-case-1"),
            make_result("test-case-2", status="fail", score=0.2, raw_output="oops"),
        ]

        async with EvalflowDB(db_path) as db:
            await db.save_run(run)
            await db.save_results(run.id, results)

            saved_results = await db.get_run_results(run.id)

        assert len(saved_results) == 2
        assert saved_results[1]["status"] == RunStatus.fail.value
        assert saved_results[1]["raw_output"] == "oops"

    @pytest.mark.asyncio
    async def test_list_runs_limit_and_failed_only(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        run_a = make_run("20260325-aaaaaaaaaaaa", status="pass")
        run_b = make_run("20260325-bbbbbbbbbbbb", status="fail", overall_score=0.2)
        run_c = make_run("20260325-cccccccccccc", status="error", overall_score=0.0)

        async with EvalflowDB(db_path) as db:
            for run in (run_a, run_b, run_c):
                await db.save_run(run)

            limited = await db.list_runs(limit=2)
            failed_only = await db.list_runs(limit=10, failed_only=True)

        assert len(limited) == 2
        assert [item["status"] for item in failed_only] == ["fail"]

    @pytest.mark.asyncio
    async def test_baseline_save_and_retrieve_latest(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        older = make_run(
            "20260324-aaaaaaaaaaaa",
            created_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
            overall_score=0.6,
        )
        newer = make_run(
            "20260325-bbbbbbbbbbbb",
            created_at=datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
            overall_score=0.9,
        )

        async with EvalflowDB(db_path) as db:
            await db.save_run(older)
            await db.save_run(newer)
            await db.save_baseline(older)
            await db.save_baseline(newer)

            baseline = await db.get_baseline("dataset-hash")

        assert baseline is not None
        assert baseline["run_id"] == newer.id
        assert baseline["scores"]["overall_score"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_find_run_by_prefix(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        run = make_run("20260325-abc123def456")

        async with EvalflowDB(db_path) as db:
            await db.save_run(run)
            found = await db.find_run_by_prefix("20260325-abc1")

        assert found is not None
        assert found["id"] == run.id

    @pytest.mark.asyncio
    async def test_sql_injection_attempt_does_not_break_queries(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"
        malicious_id = "20260325-bad'; DROP TABLE runs; --"
        run = make_run(malicious_id)

        async with EvalflowDB(db_path) as db:
            await db.save_run(run)
            saved = await db.get_run(malicious_id)
            runs = await db.list_runs(limit=10)

        assert saved is not None
        assert any(item["id"] == malicious_id for item in runs)

    @pytest.mark.asyncio
    async def test_file_permissions_best_effort(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".evalflow" / "runs.db"

        async with EvalflowDB(db_path):
            pass

        assert db_path.exists()
        if os.name != "nt":
            mode = db_path.stat().st_mode & 0o777
            assert mode == 0o600


class TestResponseCache:
    def test_cache_hit_and_miss(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")
        key = cache._make_key("openai", "gpt-4o-mini", "hello")

        assert cache.get(key) is None

        cache.set(key, "world")

        assert cache.get(key) == "world"

    def test_different_models_have_different_keys(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")
        key_a = cache._make_key("openai", "gpt-4o", "prompt")
        key_b = cache._make_key("openai", "gpt-4o-mini", "prompt")
        cache.set(key_a, "response-a")
        cache.set(key_b, "response-b")

        assert cache.get(key_a) == "response-a"
        assert cache.get(key_b) == "response-b"

    def test_clear_removes_entries(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")
        key = cache._make_key("openai", "gpt-4o-mini", "prompt")
        cache.set(key, "response")
        cache.clear()

        assert cache.get(key) is None

    def test_stats_reports_entries(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")
        cache.set(cache._make_key("openai", "gpt-4o-mini", "prompt"), "response")

        stats = cache.stats()

        assert stats["entries"] == 1
        assert stats["size_bytes"] >= 0

    def test_prompt_helpers_use_hashed_key(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")

        cache.set_for_prompt("openai", "gpt-4o-mini", "prompt", "response")

        assert cache.get_for_prompt("openai", "gpt-4o-mini", "prompt") == "response"

    def test_get_and_set_accept_provider_model_prompt(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path / ".evalflow")

        cache.set("openai", "gpt-4o-mini", "prompt", "response")

        assert cache.get("openai", "gpt-4o-mini", "prompt") == "response"
