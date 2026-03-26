"""Configuration models for evalflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evalflow.exceptions import ConfigError


class ProviderConfig(BaseModel):
    """Provider configuration loaded from evalflow.yaml."""

    model_config = ConfigDict(frozen=False)

    api_key_env: str
    default_model: str


class ProvidersConfig(BaseModel):
    """Configured model providers."""

    model_config = ConfigDict(frozen=False)

    openai: ProviderConfig | None = None
    anthropic: ProviderConfig | None = None
    groq: ProviderConfig | None = None
    gemini: ProviderConfig | None = None
    ollama: ProviderConfig | None = None


class EvalConfig(BaseModel):
    """Eval execution settings."""

    model_config = ConfigDict(frozen=False)

    dataset: str = "evals/dataset.json"
    baseline_file: str = ".evalflow/baseline.json"
    default_provider: str = "openai"
    consistency_runs: int = Field(default=3, ge=1)


class ThresholdsConfig(BaseModel):
    """Quality and safety thresholds."""

    model_config = ConfigDict(frozen=False)

    task_success: float = Field(default=0.80, ge=0.0, le=1.0)
    relevance: float = Field(default=0.75, ge=0.0, le=1.0)
    hallucination_max: float = Field(default=0.10, ge=0.0, le=1.0)
    consistency_min: float = Field(default=0.85, ge=0.0, le=1.0)


class JudgeConfig(BaseModel):
    """LLM-as-judge settings."""

    model_config = ConfigDict(frozen=False)

    provider: str = "groq"
    model: str = "llama-3.1-8b-instant"


class PromptsConfig(BaseModel):
    """Prompt registry settings."""

    model_config = ConfigDict(frozen=False)

    directory: str = "prompts/"


class StorageConfig(BaseModel):
    """Local storage settings for run artifacts."""

    model_config = ConfigDict(frozen=False)

    store_raw_outputs: bool = True
    max_output_chars: int = Field(default=2000, ge=1)


class EvalflowConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(frozen=False)

    version: str = "1.0"
    project: str | None = None
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @model_validator(mode="after")
    def validate_default_provider(self) -> "EvalflowConfig":
        configured = {
            name
            for name, value in self.providers.model_dump().items()
            if value is not None
        }
        if configured and self.eval.default_provider not in configured:
            raise ValueError(
                f"default_provider '{self.eval.default_provider}' is not configured in providers"
            )
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> "EvalflowConfig":
        """Load and validate config with actionable user-facing errors."""

        config_path = Path(path)
        if config_path.suffix.lower() not in {".yaml", ".yml"}:
            raise ConfigError(
                "evalflow config must use a .yaml or .yml extension",
                fix="Rename the config file to evalflow.yaml",
            )
        if not config_path.exists():
            raise ConfigError("evalflow.yaml not found", fix="Run: evalflow init")

        try:
            raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            if mark is not None:
                fix = f"Check line {mark.line + 1}: {getattr(exc, 'problem', str(exc))}"
            else:
                fix = str(exc)
            raise ConfigError("evalflow.yaml is not valid YAML", fix=fix) from exc

        if raw is None:
            raise ConfigError(
                "evalflow.yaml is empty",
                fix="Run: evalflow init to create a fresh config",
            )

        if not isinstance(raw, dict):
            raise ConfigError(
                "evalflow.yaml must contain a mapping at the top level",
                fix="Start the file with key/value pairs like 'providers:' and 'eval:'",
            )

        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            first_error = exc.errors()[0]
            field = " -> ".join(str(loc) for loc in first_error["loc"])
            raise ConfigError(
                f"evalflow.yaml invalid field: {field}",
                fix=first_error["msg"],
            ) from exc
