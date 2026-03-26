"""Run result models for evalflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

DEFAULT_MAX_OUTPUT_CHARS = 2000


class RunStatus(str, Enum):
    pass_ = "pass"
    fail = "fail"
    error = "error"


class TestCaseResult(BaseModel):
    """Outcome for a single test case."""

    model_config = ConfigDict(frozen=False)

    test_case_id: str
    status: RunStatus
    score: float | None = None
    exact_match_score: float | None = None
    embedding_score: float | None = None
    consistency_score: float | None = None
    judge_score: float | None = None
    raw_output: str | None = None
    error: str | None = None

    @field_validator(
        "score",
        "exact_match_score",
        "embedding_score",
        "consistency_score",
        "judge_score",
    )
    @classmethod
    def validate_score_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("scores must be between 0 and 1")
        return value

    @field_validator("raw_output")
    @classmethod
    def truncate_raw_output(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return value
        max_output_chars = DEFAULT_MAX_OUTPUT_CHARS
        if info.context and isinstance(info.context.get("max_output_chars"), int):
            max_output_chars = info.context["max_output_chars"]
        return value[:max_output_chars]


class BaselineComparison(BaseModel):
    """Comparison of a run against its stored baseline."""

    model_config = ConfigDict(frozen=False)

    baseline_run_id: str
    baseline_score: float = Field(ge=0.0, le=1.0)
    current_score: float = Field(ge=0.0, le=1.0)
    delta: float
    regression: bool


class EvalRun(BaseModel):
    """Complete eval run metadata and results."""

    model_config = ConfigDict(frozen=False)

    id: str
    created_at: datetime
    provider: str
    model: str
    dataset_hash: str
    prompt_version_hash: str | None = None
    status: RunStatus
    overall_score: float = Field(ge=0.0, le=1.0)
    duration_ms: float = Field(ge=0.0)
    results: list[TestCaseResult] = Field(default_factory=list)
