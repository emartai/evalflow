"""Base provider interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    api_key: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout: float = 60.0


@dataclass
class ProviderResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


class BaseProvider(ABC):
    """Abstract interface for provider adapters."""

    @abstractmethod
    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        """Complete a prompt and return normalized output."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return whether the provider appears healthy."""

    @classmethod
    @abstractmethod
    def provider_name(cls) -> str:
        """Return the provider registry name."""
