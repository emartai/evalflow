"""Consistency scoring for repeated model runs."""

from __future__ import annotations

import asyncio

import numpy as np

from evalflow.engine.base import BaseProvider, ProviderConfig


class ConsistencyEvaluator:
    """Estimate response consistency by comparing repeated generations."""

    async def evaluate(
        self,
        prompt: str,
        provider: BaseProvider,
        provider_config: ProviderConfig,
        runs: int = 3,
    ) -> float:
        """
        Run the same prompt multiple times and score response similarity.

        1. Run the prompt `runs` times concurrently.
        2. Embed each response.
        3. Compute pairwise cosine similarities.
        4. Return the mean similarity.
        """

        if runs <= 1:
            return 1.0

        responses = await asyncio.gather(
            *[provider.complete(prompt, provider_config) for _ in range(runs)]
        )
        contents = [response.content for response in responses]
        if len(set(contents)) == 1:
            return 1.0

        from evalflow.engine import methods as methods_module

        embedding_evaluator = methods_module.get_embedding_evaluator()
        model = embedding_evaluator._load_model()
        embeddings = [
            np.asarray(vector, dtype=float)
            for vector in model.encode(contents)
        ]

        similarities: list[float] = []
        for index, embedding in enumerate(embeddings):
            for other in embeddings[index + 1 :]:
                similarities.append(
                    embedding_evaluator._cosine_similarity(embedding, other)
                )

        if not similarities:
            return 1.0
        return float(sum(similarities) / len(similarities))
