"""YAML-backed prompt registry."""

from __future__ import annotations

from datetime import date
import difflib
from pathlib import Path
import re
from typing import Any

import yaml

from evalflow.exceptions import PromptNotFoundError
from evalflow.models import PromptStatus, PromptVersion

VALID_PROMPT_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_SUFFIXES = {".yaml", ".yml"}


def safe_resolve(user_path: str, base_dir: Path) -> Path:
    """Resolve a user-supplied path, preventing path traversal."""

    resolved = (base_dir / user_path).resolve()
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path traversal detected: {user_path}")
    return resolved


class PromptRegistry:
    """Manage prompt versions stored as YAML files."""

    def __init__(self, prompts_dir: Path):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def list_prompts(self) -> list[PromptVersion]:
        """Return prompt files sorted by name."""

        prompts: list[PromptVersion] = []
        for path in sorted(self.prompts_dir.glob("*.y*ml")):
            prompts.append(self.load_prompt_file(path))
        return prompts

    def get_prompt(
        self, name: str, status: str = "production"
    ) -> PromptVersion | None:
        """Return the prompt matching the requested status if present."""

        prompt_path = self._prompt_path(name)
        if not prompt_path.exists():
            return None

        prompt = self.load_prompt_file(prompt_path)
        versions = self._load_versions(prompt_path)
        status_value = PromptStatus(status)
        for version in versions:
            if version.status is status_value:
                return version
        return prompt if prompt.status is status_value else None

    def create_prompt(self, name: str, author: str) -> PromptVersion:
        """Create a new prompt YAML file with draft status."""

        self._validate_name(name)
        prompt_path = self._prompt_path(name)
        if prompt_path.exists():
            raise ValueError(f"Prompt already exists: {name}")

        prompt = PromptVersion(
            id=name,
            version=1,
            status=PromptStatus.draft,
            body="Write your prompt here.",
            author=author,
            created_at=date.today(),
            tags=[],
        )
        self._write_prompt_file(prompt_path, prompt, history=[])
        return prompt

    def promote_prompt(self, name: str, target: str) -> None:
        """Update the prompt status in its YAML file."""

        prompt_path = self._prompt_path(name)
        if not prompt_path.exists():
            raise PromptNotFoundError(name)

        target_status = PromptStatus(target)
        prompt = self.load_prompt_file(prompt_path)
        prompt.status = target_status
        history = [
            version
            for version in self._load_versions(prompt_path)
            if version.version != prompt.version
        ]
        self._write_prompt_file(prompt_path, prompt, history)

    def diff_versions(self, name: str, v1: int, v2: int) -> str:
        """Return a unified diff between two stored prompt versions."""

        prompt_path = self._prompt_path(name)
        if not prompt_path.exists():
            raise PromptNotFoundError(name)

        versions = {version.version: version for version in self._load_versions(prompt_path)}
        if v1 not in versions or v2 not in versions:
            raise ValueError(f"Requested versions not found for prompt: {name}")

        diff = difflib.unified_diff(
            versions[v1].body.splitlines(),
            versions[v2].body.splitlines(),
            fromfile=f"{name}@v{v1}",
            tofile=f"{name}@v{v2}",
            lineterm="",
        )
        return "\n".join(diff)

    def load_prompt_file(self, path: Path) -> PromptVersion:
        """Load a prompt YAML file with safe parsing."""

        safe_path = safe_resolve(path.name, self.prompts_dir)
        if safe_path.suffix not in ALLOWED_SUFFIXES:
            raise ValueError(f"Unsupported prompt file extension: {safe_path.suffix}")

        raw = yaml.safe_load(safe_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Prompt file must contain a mapping: {safe_path.name}")

        current = {key: raw[key] for key in ("id", "version", "status", "body", "author", "created_at", "tags") if key in raw}
        return PromptVersion.model_validate(current)

    def _load_versions(self, path: Path) -> list[PromptVersion]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Prompt file must contain a mapping: {path.name}")

        versions: list[PromptVersion] = []
        current = {key: raw[key] for key in ("id", "version", "status", "body", "author", "created_at", "tags") if key in raw}
        versions.append(PromptVersion.model_validate(current))
        for item in raw.get("history", []):
            versions.append(PromptVersion.model_validate(item))
        return sorted(versions, key=lambda prompt: prompt.version)

    def _write_prompt_file(
        self, path: Path, prompt: PromptVersion, history: list[PromptVersion]
    ) -> None:
        payload: dict[str, Any] = prompt.model_dump(mode="json")
        if history:
            payload["history"] = [item.model_dump(mode="json") for item in sorted(history, key=lambda version: version.version)]
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _prompt_path(self, name: str) -> Path:
        self._validate_name(name)
        return safe_resolve(f"{name}.yaml", self.prompts_dir)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not VALID_PROMPT_NAME.fullmatch(name):
            raise ValueError("Prompt name must be lowercase kebab-case")
