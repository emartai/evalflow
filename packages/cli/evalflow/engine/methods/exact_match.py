"""Exact-match evaluation helpers."""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping, Sequence
from typing import Any


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)


class ExactMatchEvaluator:
    """Compare model output against an expected output."""

    def evaluate(self, actual: str, expected: str) -> float:
        """Return 1.0 when normalized strings match, otherwise 0.0."""

        strict_actual = self._normalize(actual)
        strict_expected = self._normalize(expected)
        if strict_actual == strict_expected:
            return 1.0

        soft_actual = self._strip_punctuation(strict_actual)
        soft_expected = self._strip_punctuation(strict_expected)
        if soft_actual == soft_expected:
            return 1.0

        return 0.0

    def evaluate_structured(self, actual: str, expected: str) -> float:
        """Return 1.0 when structured payloads are semantically equal."""

        try:
            actual_value = json.loads(actual)
            expected_value = json.loads(expected)
        except json.JSONDecodeError:
            return 0.0

        return 1.0 if self._canonicalize(actual_value) == self._canonicalize(expected_value) else 0.0

    @staticmethod
    def _normalize(value: str) -> str:
        collapsed = _WHITESPACE_RE.sub(" ", value.strip().lower())
        return collapsed

    @staticmethod
    def _strip_punctuation(value: str) -> str:
        no_punctuation = value.translate(_PUNCT_TRANSLATION)
        return _WHITESPACE_RE.sub(" ", no_punctuation).strip()

    @classmethod
    def _canonicalize(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: cls._canonicalize(val)
                for key, val in sorted(value.items(), key=lambda item: item[0])
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._canonicalize(item) for item in value]
        if isinstance(value, str):
            return cls._normalize(value)
        return value
