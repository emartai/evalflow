"""Provider registry and config resolution helpers."""

from __future__ import annotations

from importlib import import_module
import os
from typing import TYPE_CHECKING

from evalflow.engine.base import ProviderConfig
from evalflow.exceptions import ConfigError, MissingAPIKeyError
from evalflow.models import EvalflowConfig

if TYPE_CHECKING:
    from evalflow.engine.base import BaseProvider

PROVIDER_REGISTRY: dict[str, object] = {
    "openai": ("evalflow.engine.providers.openai", "OpenAIProvider"),
    "anthropic": ("evalflow.engine.providers.anthropic", "AnthropicProvider"),
    "groq": ("evalflow.engine.providers.groq", "GroqProvider"),
    "gemini": ("evalflow.engine.providers.gemini", "GeminiProvider"),
    "ollama": ("evalflow.engine.providers.ollama", "OllamaProvider"),
}


def get_provider(name: str) -> type["BaseProvider"]:
    """Return the provider class for a configured registry name."""

    if name not in PROVIDER_REGISTRY:
        raise ConfigError(
            f"Unknown provider: {name}",
            fix=f"Valid providers: {', '.join(PROVIDER_REGISTRY.keys())}",
        )
    entry = PROVIDER_REGISTRY[name]
    if isinstance(entry, tuple):
        module_name, class_name = entry
        module = import_module(module_name)
        return getattr(module, class_name)

    if isinstance(entry, type):
        return entry

    raise ConfigError(
        f"Provider registry entry for '{name}' is invalid",
        fix="Register a provider class or (module, class) tuple",
    )


def resolve_provider_config(
    provider_name: str,
    config: EvalflowConfig,
    *,
    allow_missing_api_key: bool = False,
) -> ProviderConfig:
    provider_settings = getattr(config.providers, provider_name, None)
    if provider_settings is None:
        raise ConfigError(
            f"Provider '{provider_name}' is not configured",
            fix=f"Add providers.{provider_name} to evalflow.yaml",
        )

    api_key = ""
    if provider_settings.api_key_env:
        api_key = os.environ.get(provider_settings.api_key_env, "")
        if not api_key and provider_name != "ollama" and not allow_missing_api_key:
            raise MissingAPIKeyError(provider_name, provider_settings.api_key_env)

    return ProviderConfig(api_key=api_key, model=provider_settings.default_model)
