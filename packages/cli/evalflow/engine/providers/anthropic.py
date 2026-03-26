"""Anthropic provider implementation."""

from __future__ import annotations

import asyncio
from time import perf_counter

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.exceptions import ProviderError

RETRY_STATUS_CODES = {429, 502, 503}
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 10.0


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        client_factory=None,
        health_config: ProviderConfig | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_client
        self._health_config = health_config

    @classmethod
    def provider_name(cls) -> str:
        return "anthropic"

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            client = self._client_factory(config)
            start = perf_counter()
            try:
                response = await client.messages.create(
                    model=config.model,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                latency_ms = (perf_counter() - start) * 1000.0
                text_parts = [
                    getattr(block, "text", "")
                    for block in getattr(response, "content", [])
                    if getattr(block, "type", "text") == "text"
                ]
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
                return ProviderResponse(
                    content="".join(text_parts),
                    model=getattr(response, "model", config.model),
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                last_error = exc
                status_code = self._extract_status_code(exc)
                if status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                    delay = min(BASE_DELAY_SECONDS * (2**attempt), MAX_DELAY_SECONDS)
                    await asyncio.sleep(delay)
                    continue
                raise self._wrap_error(exc) from exc

        assert last_error is not None
        raise self._wrap_error(last_error)

    async def health_check(self) -> bool:
        probe_config = self._health_config or ProviderConfig(
            api_key="",
            model="claude-3-haiku-20240307",
        )
        client = self._client_factory(probe_config)
        try:
            await client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    def _build_client(self, config: ProviderConfig):
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=config.api_key, timeout=config.timeout, max_retries=0)

    @classmethod
    def _wrap_error(cls, exc: Exception) -> ProviderError:
        status_code = cls._extract_status_code(exc) or 0
        message = str(exc) or exc.__class__.__name__
        return ProviderError("anthropic", f"Anthropic request failed: {message}", status_code)
