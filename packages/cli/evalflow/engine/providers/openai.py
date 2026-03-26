"""OpenAI provider implementation."""

from __future__ import annotations

import asyncio
from importlib import import_module
from time import perf_counter

import httpx

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.exceptions import ProviderError

RETRY_STATUS_CODES = {429, 502, 503}
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 10.0


class OpenAIProvider(BaseProvider):
    """OpenAI provider using the async OpenAI SDK."""

    def __init__(
        self,
        client_factory=None,
        health_config: ProviderConfig | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_client
        self._health_config = health_config

    @classmethod
    def provider_name(cls) -> str:
        return "openai"

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            client = self._client_factory(config)
            start = perf_counter()
            try:
                response = await client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                latency_ms = (perf_counter() - start) * 1000.0
                usage = getattr(response, "usage", None)
                choice = response.choices[0]
                content = choice.message.content or ""
                return ProviderResponse(
                    content=content,
                    model=getattr(response, "model", config.model),
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
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
            model="gpt-4o-mini",
        )
        client = self._client_factory(probe_config)
        try:
            await client.models.list()
            return True
        except Exception:
            return False

    def _build_client(self, config: ProviderConfig) -> object:
        openai_module = import_module("openai")
        async_openai = getattr(openai_module, "AsyncOpenAI")
        timeout = httpx.Timeout(config.timeout, connect=30.0, read=60.0)
        return async_openai(
            api_key=config.api_key,
            timeout=timeout,
            max_retries=0,
        )

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

    @staticmethod
    def _wrap_error(exc: Exception) -> ProviderError:
        class_name = exc.__class__.__name__
        if class_name == "APIStatusError":
            status_code = exc.status_code or 0
            return ProviderError(
                "openai",
                f"OpenAI API request failed: {status_code}",
                status_code,
            )
        if class_name in {"APITimeoutError", "APIConnectionError"}:
            return ProviderError("openai", "OpenAI request failed due to a connection problem")

        status_code = OpenAIProvider._extract_status_code(exc) or 0
        message = str(exc) or exc.__class__.__name__
        return ProviderError("openai", f"OpenAI request failed: {message}", status_code)
