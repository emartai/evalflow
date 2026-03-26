"""Ollama provider implementation."""

from __future__ import annotations

import asyncio
from time import perf_counter

import httpx

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.exceptions import ProviderError

BASE_URL = "http://localhost:11434"
RETRY_STATUS_CODES = {429, 502, 503}
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 10.0


class OllamaProvider(BaseProvider):
    def __init__(
        self,
        client_factory=None,
        health_config: ProviderConfig | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_client
        self._health_config = health_config

    @classmethod
    def provider_name(cls) -> str:
        return "ollama"

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            client = self._client_factory()
            start = perf_counter()
            try:
                response = await client.post(
                    f"{BASE_URL}/api/generate",
                    json={
                        "model": config.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": config.temperature,
                            "num_predict": config.max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                latency_ms = (perf_counter() - start) * 1000.0
                prompt_tokens = data.get("prompt_eval_count", 0) or 0
                completion_tokens = data.get("eval_count", 0) or 0
                return ProviderResponse(
                    content=data.get("response", ""),
                    model=data.get("model", config.model),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
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
            finally:
                await self._aclose(client)

        assert last_error is not None
        raise self._wrap_error(last_error)

    async def health_check(self) -> bool:
        client = self._client_factory()
        try:
            response = await client.get(f"{BASE_URL}/api/tags")
            response.raise_for_status()
            return True
        except Exception:
            return False
        finally:
            await self._aclose(client)

    def _build_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(60.0, connect=30.0, read=60.0)
        return httpx.AsyncClient(timeout=timeout)

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
    def _wrap_error(cls, exc: Exception) -> ProviderError:
        if isinstance(exc, httpx.ConnectError):
            return ProviderError(
                "ollama",
                "Ollama is not running. Start it with: ollama serve",
            )
        status_code = cls._extract_status_code(exc) or 0
        message = str(exc) or exc.__class__.__name__
        return ProviderError("ollama", f"Ollama request failed: {message}", status_code)
