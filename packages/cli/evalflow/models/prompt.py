"""Prompt registry models."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PromptStatus(str, Enum):
    draft = "draft"
    staging = "staging"
    production = "production"


class PromptVersion(BaseModel):
    """Stored prompt version metadata."""

    model_config = ConfigDict(frozen=False)

    id: str
    version: int = Field(ge=1)
    status: PromptStatus
    body: str
    author: str
    created_at: date
    tags: list[str] = Field(default_factory=list)
