"""Eval method tests for prompts 6 and 7."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from evalflow.engine.base import BaseProvider, ProviderConfig, ProviderResponse
from evalflow.engine.methods import EmbeddingEvaluator, ExactMatchEvaluator, get_embedding_evaluator
from evalflow.engine.methods.consistency import ConsistencyEvaluator
from evalflow.engine.methods.judge import JUDGE_SYSTEM_PROMPT, LLMJudgeEvaluator
import evalflow.engine.methods as methods_module
from evalflow.exceptions import EvalflowError


class TestExactMatch:
    def test_exact_match_returns_1(self) -> None:
        result = ExactMatchEvaluator().evaluate("hello world", "hello world")
        assert result == 1.0

    def test_case_insensitive(self) -> None:
        result = ExactMatchEvaluator().evaluate("Hello", "hello")
        assert result == 1.0

    def test_whitespace_normalized(self) -> None:
        result = ExactMatchEvaluator().evaluate("hello  world", "hello world")
        assert result == 1.0

    def test_punctuation_soft_match(self) -> None:
        result = ExactMatchEvaluator().evaluate("Hello, world!", "hello world")
        assert result == 1.0

    def test_no_match_returns_0(self) -> None:
        result = ExactMatchEvaluator().evaluate("completely different", "text here")
        assert result == 0.0

    def test_empty_strings(self) -> None:
        evaluator = ExactMatchEvaluator()
        assert evaluator.evaluate("", "") == 1.0
        assert evaluator.evaluate("", "hello") == 0.0

    def test_evaluate_structured_matches_semantically(self) -> None:
        evaluator = ExactMatchEvaluator()
        actual = '{"b": ["Hello", 2], "a": 1}'
        expected = '{"a": 1, "b": ["hello", 2]}'
        assert evaluator.evaluate_structured(actual, expected) == 1.0

    def test_evaluate_structured_invalid_json_returns_0(self) -> None:
        evaluator = ExactMatchEvaluator()
        assert evaluator.evaluate_structured("not-json", '{"a": 1}') == 0.0


class _FakeSentenceTransformer:
    def __init__(self, model_name: str, **kwargs) -> None:
        self.model_name = model_name
        self.kwargs = kwargs
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]):
        self.calls.append(texts)
        if texts == ["similar actual", "similar expected"]:
            return np.array([[1.0, 0.0], [1.0, 0.0]])
        if texts == ["different actual", "different expected"]:
            return np.array([[1.0, 0.0], [-1.0, 0.0]])
        if texts == ["Same response", "Same response", "Same response"]:
            return np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
        if texts == ["alpha", "beta", "gamma"]:
            return np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0]])
        return np.array([[0.0, 0.0], [1.0, 0.0]])


class TestEmbeddingSimilarity:
    def test_similar_returns_high_score(self) -> None:
        fake_model = _FakeSentenceTransformer(EmbeddingEvaluator.MODEL_NAME)
        evaluator = EmbeddingEvaluator()
        evaluator._model = fake_model

        score = evaluator.evaluate("similar actual", "similar expected")

        assert score == pytest.approx(1.0)

    def test_different_returns_low_score(self) -> None:
        fake_model = _FakeSentenceTransformer(EmbeddingEvaluator.MODEL_NAME)
        evaluator = EmbeddingEvaluator()
        evaluator._model = fake_model

        score = evaluator.evaluate("different actual", "different expected")

        assert score == pytest.approx(0.0)

    def test_lazy_loads_model(self) -> None:
        fake_module = SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
        evaluator = EmbeddingEvaluator()

        assert evaluator._model is None

        with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            evaluator.evaluate("similar actual", "similar expected")

        assert isinstance(evaluator._model, _FakeSentenceTransformer)
        assert evaluator._model.model_name == EmbeddingEvaluator.MODEL_NAME
        assert evaluator._model.kwargs["cache_folder"].endswith(".evalflow\\models")

    def test_import_error_raises_helpful_message(self) -> None:
        evaluator = EmbeddingEvaluator()

        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with pytest.raises(EvalflowError, match="evalflow\\[embeddings\\]"):
                evaluator._load_model()

    def test_is_available_without_package(self) -> None:
        evaluator = EmbeddingEvaluator()
        with patch("evalflow.engine.methods.embedding.importlib.util.find_spec", return_value=None):
            assert evaluator.is_available() is False

    def test_zero_vector_returns_0(self) -> None:
        fake_model = _FakeSentenceTransformer(EmbeddingEvaluator.MODEL_NAME)
        evaluator = EmbeddingEvaluator()
        evaluator._model = fake_model

        score = evaluator.evaluate("anything", "else")

        assert score == 0.0


class TestEmbeddingSingleton:
    def test_get_embedding_evaluator_returns_singleton(self) -> None:
        methods_module._embedding_evaluator = None

        first = get_embedding_evaluator()
        second = get_embedding_evaluator()

        assert first is second


class _MockProvider(BaseProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        self.last_prompt = prompt
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return ProviderResponse(
            content=response,
            model=config.model,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=1.0,
        )

    async def health_check(self) -> bool:
        return True

    @classmethod
    def provider_name(cls) -> str:
        return "mock"


class TestConsistency:
    @pytest.mark.asyncio
    async def test_identical_responses_score_1(self) -> None:
        provider = _MockProvider(["Same response"])
        evaluator = ConsistencyEvaluator()
        fake_model = _FakeSentenceTransformer(EmbeddingEvaluator.MODEL_NAME)
        methods_module._embedding_evaluator = EmbeddingEvaluator()
        methods_module._embedding_evaluator._model = fake_model

        score = await evaluator.evaluate(
            "test",
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="mock-model"),
            runs=3,
        )

        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_varied_responses_lower_score(self) -> None:
        provider = _MockProvider(["alpha", "beta", "gamma"])
        evaluator = ConsistencyEvaluator()
        methods_module._embedding_evaluator = EmbeddingEvaluator()
        methods_module._embedding_evaluator._model = _FakeSentenceTransformer(
            EmbeddingEvaluator.MODEL_NAME
        )

        score = await evaluator.evaluate(
            "test",
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="mock-model"),
            runs=3,
        )

        assert score < 0.8

    @pytest.mark.asyncio
    async def test_runs_correct_number_of_times(self) -> None:
        provider = _MockProvider(["alpha", "beta", "gamma"])
        evaluator = ConsistencyEvaluator()
        methods_module._embedding_evaluator = EmbeddingEvaluator()
        methods_module._embedding_evaluator._model = _FakeSentenceTransformer(
            EmbeddingEvaluator.MODEL_NAME
        )

        await evaluator.evaluate(
            "test",
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="mock-model"),
            runs=3,
        )

        assert provider.call_count == 3


class TestLLMJudge:
    @pytest.mark.asyncio
    async def test_valid_json_response_parsed(self) -> None:
        provider = _MockProvider(
            ['{"score": 0.9, "grounded": true, "reasoning": "Good match."}']
        )
        evaluator = LLMJudgeEvaluator(
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="judge-model"),
        )

        result = await evaluator.evaluate(
            input_text="input",
            expected="expected",
            actual="actual",
            context="ctx",
        )

        assert result.score == pytest.approx(0.9)
        assert result.grounded is True
        assert result.reasoning == "Good match."
        assert result.error is None
        assert JUDGE_SYSTEM_PROMPT in (provider.last_prompt or "")

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error_result(self) -> None:
        provider = _MockProvider(["not valid json"])
        evaluator = LLMJudgeEvaluator(
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="judge-model"),
        )

        result = await evaluator.evaluate(
            input_text="input",
            expected="expected",
            actual="actual",
        )

        assert result.error is not None
        assert result.score == pytest.approx(0.5)
        assert result.grounded is False

    @pytest.mark.asyncio
    async def test_score_clamped_to_range(self) -> None:
        provider = _MockProvider(
            ['{"score": 1.8, "grounded": false, "reasoning": "Too high."}']
        )
        evaluator = LLMJudgeEvaluator(
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="judge-model"),
        )

        result = await evaluator.evaluate(
            input_text="input",
            expected="expected",
            actual="actual",
        )

        assert result.score == pytest.approx(1.0)
        assert result.grounded is False

    @pytest.mark.asyncio
    async def test_missing_fields_returns_error_result(self) -> None:
        provider = _MockProvider(['{"score": 0.8}'])
        evaluator = LLMJudgeEvaluator(
            provider,
            ProviderConfig(api_key="sk-fake-key-for-testing", model="judge-model"),
        )

        result = await evaluator.evaluate(
            input_text="input",
            expected="expected",
            actual="actual",
        )

        assert result.score == pytest.approx(0.5)
        assert result.error is not None
