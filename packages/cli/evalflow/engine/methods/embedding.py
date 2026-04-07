"""Embedding-similarity evaluation helpers."""

from __future__ import annotations

import importlib.util
import os
import warnings
from pathlib import Path

import numpy as np

from evalflow.exceptions import EvalflowError
from evalflow.output.rich_output import print_info


class EmbeddingEvaluator:
    """Compute cosine similarity using a local sentence-transformers model."""

    MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        self._model = None
        self._cache_dir = Path(".evalflow") / "models"

    def _load_model(self):
        """Lazy load sentence-transformers on first use."""

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EvalflowError(
                    "sentence-transformers not installed.\n"
                    "Install with: pip install 'evalflow[embeddings]'"
                ) from exc
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            if not any(self._cache_dir.iterdir()):
                print_info("Downloading embedding model (80MB, one-time)...")
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
                warnings.filterwarnings("ignore", category=UserWarning, module="sentence_transformers")
                self._model = SentenceTransformer(
                    self.MODEL_NAME,
                    cache_folder=str(self._cache_dir),
                )
        return self._model

    def evaluate(self, actual: str, expected: str) -> float:
        """Return a cosine-similarity score in the [0, 1] range."""

        model = self._load_model()
        embeddings = model.encode([actual, expected])
        actual_vector = np.asarray(embeddings[0], dtype=float)
        expected_vector = np.asarray(embeddings[1], dtype=float)
        return float(self._cosine_similarity(actual_vector, expected_vector))

    def is_available(self) -> bool:
        """Return whether sentence-transformers can be imported."""

        return importlib.util.find_spec("sentence_transformers") is not None

    @staticmethod
    def _cosine_similarity(actual: np.ndarray, expected: np.ndarray) -> float:
        actual_norm = float(np.linalg.norm(actual))
        expected_norm = float(np.linalg.norm(expected))
        if actual_norm == 0.0 or expected_norm == 0.0:
            return 0.0

        cosine = float(np.dot(actual, expected) / (actual_norm * expected_norm))
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))
