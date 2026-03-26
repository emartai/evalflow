"""Prompt registry tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from evalflow import get_prompt
from evalflow.exceptions import PromptNotFoundError
from evalflow.registry.prompt_registry import PromptRegistry


def test_create_and_get_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = PromptRegistry(tmp_path / "prompts")

    prompt = registry.create_prompt("summarization", author="emmanuel")
    fetched = registry.get_prompt("summarization", "draft")

    assert prompt.id == "summarization"
    assert fetched is not None
    assert fetched.status.value == "draft"


def test_promote_prompt_updates_status(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path / "prompts")
    registry.create_prompt("summarization", author="emmanuel")

    registry.promote_prompt("summarization", "production")
    prompt = registry.get_prompt("summarization", "production")

    assert prompt is not None
    assert prompt.status.value == "production"


def test_diff_versions_returns_diff(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path / "prompts")
    path = tmp_path / "prompts" / "summarization.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": "summarization",
        "version": 2,
        "status": "production",
        "body": "line one\nline three",
        "author": "emmanuel",
        "created_at": date(2024, 3, 2).isoformat(),
        "tags": [],
        "history": [
            {
                "id": "summarization",
                "version": 1,
                "status": "draft",
                "body": "line one\nline two",
                "author": "emmanuel",
                "created_at": date(2024, 3, 1).isoformat(),
                "tags": [],
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    diff = registry.diff_versions("summarization", 1, 2)

    assert "line three" in diff


def test_get_prompt_public_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = PromptRegistry(tmp_path / "prompts")
    registry.create_prompt("summarization", author="emmanuel")
    registry.promote_prompt("summarization", "production")

    body = get_prompt("summarization")

    assert body == "Write your prompt here."


def test_get_prompt_raises_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(PromptNotFoundError):
        get_prompt("missing")
