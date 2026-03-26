"""Exception types for evalflow."""

from __future__ import annotations

from evalflow.urls import PROVIDERS_DOCS_URL


class EvalflowError(Exception):
    """Base class for all evalflow-specific errors."""


class ConfigError(EvalflowError):
    """Raised for invalid or missing configuration."""

    def __init__(self, message: str, fix: str = "", link: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.link = link


class MissingAPIKeyError(ConfigError):
    """Raised when a provider API key is missing from the environment."""

    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(
            f"Missing API key for {provider}",
            fix=f'Set {env_var} in your environment:\nexport {env_var}="your-key-here"',
            link=f"{PROVIDERS_DOCS_URL}{provider}",
        )


class ProviderError(EvalflowError):
    """Raised when a provider request fails."""

    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int = 0,
        fix: str = "",
        link: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        if not fix:
            if status_code in {401, 403}:
                fix = f"Check your {provider.upper()} API key and provider configuration, then try again"
            elif status_code == 429:
                fix = "Rate limit exceeded. Wait a moment and try again"
            elif "connection" in message.lower():
                fix = "Check your internet connection or provider availability, then try again"
        self.fix = fix
        self.link = link or f"{PROVIDERS_DOCS_URL}{provider}"


class DatasetError(EvalflowError):
    """Raised for dataset loading or validation issues."""

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix


class StorageError(EvalflowError):
    """Raised for persistence-layer failures."""

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix


class PromptNotFoundError(EvalflowError):
    """Raised when a named prompt cannot be found."""

    def __init__(self, name: str) -> None:
        message = f"Prompt not found: {name}"
        super().__init__(message)
        self.message = message
        self.fix = f"Create it with: evalflow prompt create {name}"
