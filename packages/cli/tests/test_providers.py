"""Provider and exception tests."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from evalflow.engine.base import ProviderConfig
from evalflow.engine.providers import get_provider, resolve_provider_config
from evalflow.engine.providers.anthropic import AnthropicProvider
from evalflow.engine.providers.gemini import GeminiProvider
from evalflow.engine.providers.groq import GroqProvider
from evalflow.engine.providers.ollama import OllamaProvider
from evalflow.engine.providers.openai import OpenAIProvider
from evalflow.exceptions import ConfigError, MissingAPIKeyError, ProviderError
from evalflow.models import EvalflowConfig


class _FakeChatCompletions:
    def __init__(self, responses):
        self.responses = list(responses)

    async def create(self, **kwargs):
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeModels:
    def __init__(self, error: Exception | None = None):
        self.error = error

    async def list(self):
        if self.error is not None:
            raise self.error
        return []


class _FakeClient:
    def __init__(self, responses, health_error: Exception | None = None):
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(responses))
        self.models = _FakeModels(health_error)


class _FakeAnthropicMessages:
    def __init__(self, responses):
        self.responses = list(responses)

    async def create(self, **kwargs):
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAnthropicClient:
    def __init__(self, responses, health_error: Exception | None = None):
        self.messages = _FakeAnthropicMessages(responses)
        self.models = _FakeModels(health_error)


class _FakeHTTPResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("POST", "https://example.com")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.closed = False
        self.last_get_kwargs = None

    async def post(self, *args, **kwargs):
        item = self.post_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, *args, **kwargs):
        self.last_get_kwargs = kwargs
        item = self.get_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        self.closed = True


def _response(content: str, model: str = "gpt-4o-mini"):
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


class TestProviderRegistry:
    def test_get_provider_returns_openai(self) -> None:
        provider_cls = get_provider("openai")

        assert provider_cls.provider_name() == "openai"

    def test_get_provider_raises_for_unknown_provider(self) -> None:
        with pytest.raises(ConfigError, match="Unknown provider"):
            get_provider("unknown")

    def test_resolve_provider_config_reads_env(self) -> None:
        config = EvalflowConfig.model_validate(
            {
                "providers": {
                    "openai": {
                        "api_key_env": "OPENAI_API_KEY",
                        "default_model": "gpt-4o-mini",
                    }
                },
                "eval": {"default_provider": "openai"},
            }
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-fake-key-for-testing"}, clear=False):
            provider_config = resolve_provider_config("openai", config)

        assert provider_config.api_key == "sk-fake-key-for-testing"
        assert provider_config.model == "gpt-4o-mini"

    def test_resolve_provider_config_requires_api_key(self) -> None:
        config = EvalflowConfig.model_validate(
            {
                "providers": {
                    "openai": {
                        "api_key_env": "OPENAI_API_KEY",
                        "default_model": "gpt-4o-mini",
                    }
                },
                "eval": {"default_provider": "openai"},
            }
        )

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingAPIKeyError, match="Missing API key"):
                resolve_provider_config("openai", config)


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_complete_returns_normalized_response(self) -> None:
        client = _FakeClient([_response("hello world")])
        provider = OpenAIProvider(client_factory=lambda config: client)

        result = await provider.complete(
            "Say hello",
            ProviderConfig(api_key="sk-fake-key-for-testing", model="gpt-4o-mini"),
        )

        assert result.content == "hello world"
        assert result.model == "gpt-4o-mini"
        assert result.prompt_tokens == 11
        assert result.completion_tokens == 7
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_complete_retries_transient_status_codes(self) -> None:
        transient = httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
            response=httpx.Response(429),
        )
        client = _FakeClient([transient, _response("ok after retry")])
        provider = OpenAIProvider(client_factory=lambda config: client)

        with patch("evalflow.engine.providers.openai.asyncio.sleep") as sleep_mock:
            result = await provider.complete(
                "retry me",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="gpt-4o-mini"),
            )

        assert result.content == "ok after retry"
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_wraps_failure_in_provider_error(self) -> None:
        client = _FakeClient([RuntimeError("boom")])
        provider = OpenAIProvider(client_factory=lambda config: client)

        with pytest.raises(ProviderError, match="OpenAI request failed"):
            await provider.complete(
                "fail",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="gpt-4o-mini"),
            )

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_models_list_succeeds(self) -> None:
        client = _FakeClient([_response("unused")])
        probe_config = ProviderConfig(api_key="sk-fake-key-for-testing", model="gpt-4o-mini")
        provider = OpenAIProvider(
            client_factory=lambda config: client,
            health_config=probe_config,
        )

        result = await provider.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self) -> None:
        client = _FakeClient([_response("unused")], health_error=RuntimeError("down"))
        provider = OpenAIProvider(
            client_factory=lambda config: client,
            health_config=ProviderConfig(api_key="sk-fake-key-for-testing", model="gpt-4o-mini"),
        )

        result = await provider.health_check()

        assert result is False


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        response = SimpleNamespace(
            model="claude-3-haiku-20240307",
            content=[SimpleNamespace(type="text", text="anthropic hello")],
            usage=SimpleNamespace(input_tokens=12, output_tokens=9),
        )
        provider = AnthropicProvider(client_factory=lambda config: _FakeAnthropicClient([response]))

        result = await provider.complete(
            "hello",
            ProviderConfig(api_key="sk-fake-key-for-testing", model="claude-3-haiku-20240307"),
        )

        assert result.content == "anthropic hello"
        assert result.prompt_tokens == 12
        assert result.completion_tokens == 9

    @pytest.mark.asyncio
    async def test_retry_on_429(self) -> None:
        client = _FakeAnthropicClient(
            [
                httpx.HTTPStatusError(
                    "rate limited",
                    request=httpx.Request("POST", "https://api.anthropic.com"),
                    response=httpx.Response(429),
                ),
                SimpleNamespace(
                    model="claude-3-haiku-20240307",
                    content=[SimpleNamespace(type="text", text="ok")],
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                ),
            ]
        )
        provider = AnthropicProvider(client_factory=lambda config: client)

        with patch("evalflow.engine.providers.anthropic.asyncio.sleep") as sleep_mock:
            result = await provider.complete(
                "retry",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="claude-3-haiku-20240307"),
            )

        assert result.content == "ok"
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        provider = AnthropicProvider(
            client_factory=lambda config: _FakeAnthropicClient([RuntimeError("boom")])
        )

        with pytest.raises(ProviderError, match="Anthropic request failed"):
            await provider.complete(
                "fail",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="claude-3-haiku-20240307"),
            )


class TestGroqProvider:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        client = _FakeHTTPClient(
            post_responses=[
                _FakeHTTPResponse(
                    200,
                    {
                        "model": "llama-3.1-8b-instant",
                        "choices": [{"message": {"content": "groq hello"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 3},
                    },
                )
            ]
        )
        provider = GroqProvider(client_factory=lambda: client)

        result = await provider.complete(
            "hello",
            ProviderConfig(api_key="sk-fake-key-for-testing", model="llama-3.1-8b-instant"),
        )

        assert result.content == "groq hello"
        assert result.prompt_tokens == 4
        assert result.completion_tokens == 3

    @pytest.mark.asyncio
    async def test_retry_on_429(self) -> None:
        client = _FakeHTTPClient(
            post_responses=[
                _FakeHTTPResponse(429, {}),
                _FakeHTTPResponse(
                    200,
                    {
                        "model": "llama-3.1-8b-instant",
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    },
                ),
            ]
        )
        provider = GroqProvider(client_factory=lambda: client)

        with patch("evalflow.engine.providers.groq.asyncio.sleep") as sleep_mock:
            result = await provider.complete(
                "retry",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="llama-3.1-8b-instant"),
            )

        assert result.content == "ok"
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        provider = GroqProvider(client_factory=lambda: _FakeHTTPClient(post_responses=[RuntimeError("boom")]))

        with pytest.raises(ProviderError, match="Groq request failed"):
            await provider.complete(
                "fail",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="llama-3.1-8b-instant"),
            )

    @pytest.mark.asyncio
    async def test_health_check_uses_authorization_header(self) -> None:
        client = _FakeHTTPClient(get_responses=[_FakeHTTPResponse(200, {})])
        provider = GroqProvider(
            client_factory=lambda: client,
            health_config=ProviderConfig(api_key="sk-fake-key-for-testing", model="llama-3.1-8b-instant"),
        )

        result = await provider.health_check()

        assert result is True
        assert client.last_get_kwargs == {
            "headers": {"Authorization": "Bearer sk-fake-key-for-testing"}
        }


class TestGeminiProvider:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        provider = GeminiProvider(
            client_factory=lambda: _FakeHTTPClient(
                post_responses=[
                    _FakeHTTPResponse(
                        200,
                        {
                            "candidates": [
                                {"content": {"parts": [{"text": "gemini hello"}]}}
                            ],
                            "usageMetadata": {
                                "promptTokenCount": 6,
                                "candidatesTokenCount": 5,
                            },
                        },
                    )
                ]
            )
        )

        result = await provider.complete(
            "hello",
            ProviderConfig(api_key="sk-fake-key-for-testing", model="gemini-1.5-flash"),
        )

        assert result.content == "gemini hello"
        assert result.prompt_tokens == 6
        assert result.completion_tokens == 5

    @pytest.mark.asyncio
    async def test_retry_on_429(self) -> None:
        client = _FakeHTTPClient(
            post_responses=[
                _FakeHTTPResponse(429, {}),
                _FakeHTTPResponse(
                    200,
                    {
                        "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                        "usageMetadata": {
                            "promptTokenCount": 1,
                            "candidatesTokenCount": 1,
                        },
                    },
                ),
            ]
        )
        provider = GeminiProvider(client_factory=lambda: client)

        with patch("evalflow.engine.providers.gemini.asyncio.sleep") as sleep_mock:
            result = await provider.complete(
                "retry",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="gemini-1.5-flash"),
            )

        assert result.content == "ok"
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        provider = GeminiProvider(client_factory=lambda: _FakeHTTPClient(post_responses=[RuntimeError("boom")]))

        with pytest.raises(ProviderError, match="Gemini request failed"):
            await provider.complete(
                "fail",
                ProviderConfig(api_key="sk-fake-key-for-testing", model="gemini-1.5-flash"),
            )

    @pytest.mark.asyncio
    async def test_health_check_uses_api_key_query_param(self) -> None:
        client = _FakeHTTPClient(get_responses=[_FakeHTTPResponse(200, {})])
        provider = GeminiProvider(
            client_factory=lambda: client,
            health_config=ProviderConfig(api_key="sk-fake-key-for-testing", model="gemini-1.5-flash"),
        )

        result = await provider.health_check()

        assert result is True
        assert client.last_get_kwargs == {"params": {"key": "sk-fake-key-for-testing"}}


class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        provider = OllamaProvider(
            client_factory=lambda: _FakeHTTPClient(
                post_responses=[
                    _FakeHTTPResponse(
                        200,
                        {
                            "model": "llama3",
                            "response": "ollama hello",
                            "prompt_eval_count": 3,
                            "eval_count": 2,
                        },
                    )
                ]
            )
        )

        result = await provider.complete(
            "hello",
            ProviderConfig(api_key="", model="llama3"),
        )

        assert result.content == "ollama hello"
        assert result.prompt_tokens == 3
        assert result.completion_tokens == 2

    @pytest.mark.asyncio
    async def test_retry_on_429(self) -> None:
        client = _FakeHTTPClient(
            post_responses=[
                _FakeHTTPResponse(429, {}),
                _FakeHTTPResponse(
                    200,
                    {
                        "model": "llama3",
                        "response": "ok",
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                    },
                ),
            ]
        )
        provider = OllamaProvider(client_factory=lambda: client)

        with patch("evalflow.engine.providers.ollama.asyncio.sleep") as sleep_mock:
            result = await provider.complete(
                "retry",
                ProviderConfig(api_key="", model="llama3"),
            )

        assert result.content == "ok"
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        provider = OllamaProvider(
            client_factory=lambda: _FakeHTTPClient(
                post_responses=[
                    httpx.ConnectError(
                        "connection refused",
                        request=httpx.Request("POST", "http://localhost:11434/api/generate"),
                    )
                ]
            )
        )

        with pytest.raises(ProviderError, match="Ollama is not running"):
            await provider.complete(
                "fail",
                ProviderConfig(api_key="", model="llama3"),
            )
