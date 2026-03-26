"""LLM-as-judge evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import json

from evalflow.engine.base import BaseProvider, ProviderConfig


JUDGE_SYSTEM_PROMPT = """
You are an expert evaluator assessing LLM outputs for quality and groundedness.
You will be given an input, expected output, and actual output.
Respond with ONLY a JSON object with these fields:
{
  "score": float between 0 and 1,
  "grounded": boolean,
  "reasoning": "one sentence explanation"
}
Do not add any text outside the JSON object.
""".strip()


@dataclass
class JudgeResult:
    score: float
    grounded: bool
    reasoning: str
    error: str | None = None


class LLMJudgeEvaluator:
    """Ask a model to judge output quality and groundedness."""

    def __init__(self, judge_provider: BaseProvider, judge_config: ProviderConfig):
        self.judge_provider = judge_provider
        self.judge_config = judge_config

    async def evaluate(
        self,
        input_text: str,
        expected: str,
        actual: str,
        context: str | None = None,
    ) -> JudgeResult:
        """Send the judge prompt to an LLM and parse its JSON response."""

        prompt = self._build_prompt(
            input_text=input_text,
            expected=expected,
            actual=actual,
            context=context,
        )
        response = await self.judge_provider.complete(prompt, self.judge_config)
        return self._parse_response(response.content)

    @staticmethod
    def _build_prompt(
        *,
        input_text: str,
        expected: str,
        actual: str,
        context: str | None,
    ) -> str:
        payload = {
            "input": input_text,
            "expected_output": expected,
            "actual_output": actual,
            "context": context,
        }
        return f"{JUDGE_SYSTEM_PROMPT}\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    @staticmethod
    def _parse_response(content: str) -> JudgeResult:
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("Judge response must be a JSON object")

            score_raw = parsed["score"]
            grounded_raw = parsed["grounded"]
            reasoning_raw = parsed["reasoning"]
            if not isinstance(reasoning_raw, str):
                raise TypeError("reasoning must be a string")

            score = float(score_raw)
            grounded = bool(grounded_raw)
            reasoning = reasoning_raw.strip() or "Judge returned no reasoning."
            return JudgeResult(
                score=max(0.0, min(1.0, score)),
                grounded=grounded,
                reasoning=reasoning,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return JudgeResult(
                score=0.5,
                grounded=False,
                reasoning="Judge response could not be parsed.",
                error=str(exc),
            )
