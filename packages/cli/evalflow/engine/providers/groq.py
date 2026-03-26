"""Groq provider implementation."""

from __future__ import annotations

import asyncio
from time import perf_counter

import httpx

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.exceptions import ProviderError

BASE_URL = "https://api.groq.com/openai/v1"
RETRY_STATUS_CODES = {429, 502, 503}
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 10.0


class GroqProvider(BaseProvider):
    def __init__(
        self,
        client_factory=None,
        health_config: ProviderConfig | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_client
        self._health_config = health_config

    @classmethod
    def provider_name(cls) -> str:
        return "groq"

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        return await self._chat_completion(
            prompt=prompt,
            config=config,
            provider_name="groq",
            base_url=BASE_URL,
        )

    async def health_check(self) -> bool:
        probe_config = self._health_config or ProviderConfig(api_key="", model="")
        client = self._client_factory()
        try:
            response = await client.get(
                f"{BASE_URL}/models",
                headers={"Authorization": f"Bearer {probe_config.api_key}"},
            )
            response.raise_for_status()
            return True
        except Exception:
            return False
        finally:
            await self._aclose(client)

    def _build_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(60.0, connect=30.0, read=60.0)
        return httpx.AsyncClient(timeout=timeout)

    async def _chat_completion(
        self,
        prompt: str,
        config: ProviderConfig,
        provider_name: str,
        base_url: str,
    ) -> ProviderResponse:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            client = self._client_factory()
            start = perf_counter()
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": config.temperature,
                        "max_tokens": config.max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
                latency_ms = (perf_counter() - start) * 1000.0
                usage = data.get("usage", {})
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                return ProviderResponse(
                    content=message.get("content", ""),
                    model=data.get("model", config.model),
                    prompt_tokens=usage.get("prompt_tokens", 0) or 0,
                    completion_tokens=usage.get("completion_tokens", 0) or 0,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                last_error = exc
                status_code = self._extract_status_code(exc)
                if status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                    delay = min(BASE_DELAY_SECONDS * (2**attempt), MAX_DELAY_SECONDS)
                    await asyncio.sleep(delay)
                    continue
                raise self._wrap_error(provider_name, exc) from exc
            finally:
                await self._aclose(client)

        assert last_error is not None
        raise self._wrap_error(provider_name, last_error)

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
    async def _aclose(client: object) -> None:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    @classmethod
    def _wrap_error(cls, provider_name: str, exc: Exception) -> ProviderError:
        status_code = cls._extract_status_code(exc) or 0
        message = str(exc) or exc.__class__.__name__
        return ProviderError(provider_name, f"{provider_name.capitalize()} request failed: {message}", status_code)
