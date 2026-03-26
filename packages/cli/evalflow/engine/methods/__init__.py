"""Evaluation method helpers."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evalflow.engine.methods.consistency import ConsistencyEvaluator
    from evalflow.engine.methods.embedding import EmbeddingEvaluator
    from evalflow.engine.methods.exact_match import ExactMatchEvaluator
    from evalflow.engine.methods.judge import JUDGE_SYSTEM_PROMPT, JudgeResult, LLMJudgeEvaluator

_LAZY_EXPORTS = {
    "ConsistencyEvaluator": ("evalflow.engine.methods.consistency", "ConsistencyEvaluator"),
    "EmbeddingEvaluator": ("evalflow.engine.methods.embedding", "EmbeddingEvaluator"),
    "ExactMatchEvaluator": ("evalflow.engine.methods.exact_match", "ExactMatchEvaluator"),
    "JUDGE_SYSTEM_PROMPT": ("evalflow.engine.methods.judge", "JUDGE_SYSTEM_PROMPT"),
    "JudgeResult": ("evalflow.engine.methods.judge", "JudgeResult"),
    "LLMJudgeEvaluator": ("evalflow.engine.methods.judge", "LLMJudgeEvaluator"),
}

_embedding_evaluator: "EmbeddingEvaluator | None" = None


def get_embedding_evaluator() -> "EmbeddingEvaluator":
    """Return the shared embedding evaluator singleton."""

    global _embedding_evaluator
    if _embedding_evaluator is None:
        evaluator_cls = _load_attr("EmbeddingEvaluator")
        _embedding_evaluator = evaluator_cls()
    return _embedding_evaluator


def __getattr__(name: str) -> Any:
    """Resolve heavier method modules on first access."""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    return _load_attr(name)


def _load_attr(name: str) -> Any:
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    return getattr(module, attr_name)


__all__ = [
    "ConsistencyEvaluator",
    "EmbeddingEvaluator",
    "ExactMatchEvaluator",
    "JUDGE_SYSTEM_PROMPT",
    "JudgeResult",
    "LLMJudgeEvaluator",
    "get_embedding_evaluator",
]
