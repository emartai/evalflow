"""Dataset models for evalflow."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalflow.exceptions import DatasetError

KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EvalMethod(str, Enum):
    exact_match = "exact_match"
    embedding_similarity = "embedding_similarity"
    consistency = "consistency"
    llm_judge = "llm_judge"


class TaskType(str, Enum):
    summarization = "summarization"
    classification = "classification"
    extraction = "extraction"
    qa = "qa"
    generation = "generation"
    rewrite = "rewrite"


class EvalCaseConfig(BaseModel):
    """Per-test evaluation settings."""

    model_config = ConfigDict(frozen=False)

    methods: list[EvalMethod] = Field(default_factory=list)
    judge: bool = False
    weight: float = Field(default=1.0, gt=0.0)

    @field_validator("methods")
    @classmethod
    def validate_methods_unique(cls, value: list[EvalMethod]) -> list[EvalMethod]:
        if len(value) != len(set(value)):
            raise ValueError("eval methods must be unique per test case")
        return value


class TestCase(BaseModel):
    """One eval test case."""

    model_config = ConfigDict(frozen=False)

    id: str
    description: str
    task_type: TaskType
    input: str
    expected_output: str
    context: str | None = None
    tags: list[str] = Field(default_factory=list)
    eval_config: EvalCaseConfig = Field(default_factory=EvalCaseConfig)

    @field_validator("id")
    @classmethod
    def validate_id_kebab_case(cls, value: str) -> str:
        if not KEBAB_CASE_PATTERN.fullmatch(value):
            raise ValueError("test case id must be kebab-case")
        return value


class Dataset(BaseModel):
    """Dataset file structure."""

    model_config = ConfigDict(frozen=False)

    version: str
    test_cases: list[TestCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "Dataset":
        ids = [test_case.id for test_case in self.test_cases]
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate test case ids: {', '.join(duplicates)}")
        return self

    @classmethod
    def from_json(cls, path: str | Path) -> "Dataset":
        """Load and validate dataset content with actionable errors."""

        dataset_path = Path(path)
        if dataset_path.suffix.lower() != ".json":
            raise DatasetError(
                "dataset.json must use a .json file extension",
                fix="Rename the dataset file to end with .json",
            )
        if not dataset_path.exists():
            raise DatasetError(
                f"Dataset not found: {dataset_path}",
                fix="Create evals/dataset.json or run: evalflow init",
            )

        try:
            raw: Any = json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetError(
                "dataset.json is not valid JSON",
                fix=f"Syntax error at line {exc.lineno}: {exc.msg}",
            ) from exc

        if not isinstance(raw, dict):
            raise DatasetError(
                "dataset.json must contain an object at the top level",
                fix="Start the file with an object containing 'version' and 'test_cases'",
            )

        if "version" not in raw:
            raise DatasetError(
                "Missing 'version' field in dataset.json",
                fix='Add: "version": "1.0"',
            )

        test_cases = raw.get("test_cases")
        if not test_cases:
            raise DatasetError(
                "No test cases found in dataset.json",
                fix="Add at least one test case to the test_cases array",
            )

        ids = [tc.get("id") for tc in test_cases if isinstance(tc, dict)]
        duplicates = sorted({case_id for case_id in ids if case_id and ids.count(case_id) > 1})
        if duplicates:
            raise DatasetError(
                f"Duplicate test case IDs: {', '.join(duplicates)}",
                fix="Each test case must have a unique 'id' field",
            )

        for index, test_case in enumerate(test_cases, start=1):
            if not isinstance(test_case, dict):
                raise DatasetError(
                    f"Test case #{index} must be an object",
                    fix="Ensure every item in test_cases is a JSON object",
                )
            if not test_case.get("id"):
                raise DatasetError(f"Test case #{index} missing 'id' field")
            if not test_case.get("input"):
                raise DatasetError(f"Test case '{test_case.get('id')}' missing 'input' field")
            if not test_case.get("expected_output"):
                raise DatasetError(
                    f"Test case '{test_case.get('id')}' missing 'expected_output' field"
                )

        try:
            return cls.model_validate(raw)
        except Exception as exc:
            raise DatasetError("dataset.json is invalid", fix=str(exc)) from exc

    def compute_hash(self) -> str:
        """SHA-256 of dataset content for run tracking."""

        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()
