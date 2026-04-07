"""Public package interface for evalflow."""

from pathlib import Path

__version__ = "0.1.1"


def get_prompt(name: str, status: str = "production") -> str:
    """Return a prompt body by name and status."""

    from evalflow.exceptions import PromptNotFoundError
    from evalflow.registry.prompt_registry import PromptRegistry

    registry = PromptRegistry(Path.cwd() / "prompts")
    prompt = registry.get_prompt(name, status)
    if prompt is None:
        raise PromptNotFoundError(name)
    return prompt.body
