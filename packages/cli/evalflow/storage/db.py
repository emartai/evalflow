"""SQLite storage layer for evalflow."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from evalflow.models import EvalRun, TestCaseResult


UTC = timezone.utc


class EvalflowDB:
    """Async SQLite storage for runs, results, and baselines."""

    DEFAULT_PATH = Path(".evalflow/runs.db")

    def __init__(self, db_path: Path = DEFAULT_PATH) -> None:
        self.db_path = Path(db_path)

    async def __aenter__(self) -> "EvalflowDB":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def initialize(self) -> None:
        """Create the database and required tables if they do not exist."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        file_existed = self.db_path.exists()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    provider TEXT,
                    model TEXT,
                    dataset_hash TEXT,
                    prompt_version_hash TEXT,
                    status TEXT,
                    overall_score REAL,
                    duration_ms INTEGER
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT REFERENCES runs(id),
                    test_case_id TEXT,
                    status TEXT,
                    score REAL,
                    exact_match_score REAL,
                    embedding_score REAL,
                    consistency_score REAL,
                    judge_score REAL,
                    raw_output TEXT,
                    error TEXT
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP,
                    run_id TEXT REFERENCES runs(id),
                    dataset_hash TEXT,
                    scores_json TEXT
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id TEXT,
                    version INTEGER,
                    status TEXT,
                    body TEXT,
                    author TEXT,
                    created_at TIMESTAMP
                )
                """
            )
            await conn.commit()

        if not file_existed and self.db_path.exists():
            self._set_file_permissions()

    def _set_file_permissions(self) -> None:
        """Best-effort file permission hardening for the DB file."""

        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            # Windows and some filesystems may not fully honor chmod here.
            pass

    async def save_run(self, run: EvalRun) -> None:
        """Persist run metadata."""

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, created_at, provider, model, dataset_hash,
                    prompt_version_hash, status, overall_score, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    self._serialize_datetime(run.created_at),
                    run.provider,
                    run.model,
                    run.dataset_hash,
                    run.prompt_version_hash,
                    run.status.value,
                    run.overall_score,
                    int(run.duration_ms),
                ),
            )
            await conn.commit()

    async def save_results(self, run_id: str, results: list[TestCaseResult]) -> None:
        """Persist per-test-case results for a run."""

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
            await conn.executemany(
                """
                INSERT INTO results (
                    run_id, test_case_id, status, score, exact_match_score,
                    embedding_score, consistency_score, judge_score, raw_output, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        result.test_case_id,
                        result.status.value,
                        result.score,
                        result.exact_match_score,
                        result.embedding_score,
                        result.consistency_score,
                        result.judge_score,
                        result.raw_output,
                        result.error,
                    )
                    for result in results
                ],
            )
            await conn.commit()

    async def save_baseline(self, run: EvalRun) -> None:
        """Persist a baseline snapshot for a dataset hash."""

        scores_payload = {
            "run_id": run.id,
            "overall_score": run.overall_score,
            "results": [result.model_dump(mode="json") for result in run.results],
        }

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO baselines (created_at, run_id, dataset_hash, scores_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self._serialize_datetime(run.created_at),
                    run.id,
                    run.dataset_hash,
                    json.dumps(scores_payload),
                ),
            )
            await conn.commit()

    async def get_baseline(self, dataset_hash: str) -> dict[str, Any] | None:
        """Return the most recent baseline for a dataset hash."""

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT id, created_at, run_id, dataset_hash, scores_json
                FROM baselines
                WHERE dataset_hash = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (dataset_hash,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        baseline = dict(row)
        baseline["scores"] = json.loads(baseline.pop("scores_json"))
        return baseline

    async def list_runs(
        self,
        limit: int = 20,
        since_days: int | None = None,
        failed_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List recent runs with optional filtering."""

        query = """
            SELECT id, created_at, provider, model, dataset_hash, prompt_version_hash,
                   status, overall_score, duration_ms
            FROM runs
        """
        clauses: list[str] = []
        params: list[Any] = []

        if since_days is not None:
            since = datetime.now(UTC) - timedelta(days=since_days)
            clauses.append("datetime(created_at) >= datetime(?)")
            params.append(self._serialize_datetime(since))

        if failed_only:
            clauses.append("status = ?")
            params.append("fail")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY datetime(created_at) DESC, id DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch one run by exact ID."""

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT id, created_at, provider, model, dataset_hash, prompt_version_hash,
                       status, overall_score, duration_ms
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            )
            row = await cursor.fetchone()

        return dict(row) if row is not None else None

    async def get_run_results(self, run_id: str) -> list[dict[str, Any]]:
        """Fetch all stored results for a run."""

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT run_id, test_case_id, status, score, exact_match_score,
                       embedding_score, consistency_score, judge_score, raw_output, error
                FROM results
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            )
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def find_run_by_prefix(self, prefix: str) -> dict[str, Any] | None:
        """Find a run by ID prefix for convenience lookups."""

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT id, created_at, provider, model, dataset_hash, prompt_version_hash,
                       status, overall_score, duration_ms
                FROM runs
                WHERE id LIKE ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (f"{prefix}%",),
            )
            row = await cursor.fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def _serialize_datetime(value: datetime) -> str:
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(UTC).isoformat()
