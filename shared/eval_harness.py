"""LLM Eval Harness — LLM-as-Judge quality scoring for agent node outputs.

Usage:
    from shared.eval_harness import EvalScenario, run_eval
    result = await run_eval(scenario)
    print(result["score"], result["passed"])

Run all evals:
    pytest tests/test_llm_eval.py -v
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from shared.llm_client import LLMClient, LLMResult

logger = logging.getLogger(__name__)


@dataclass
class EvalScenario:
    name: str
    description: str
    node_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    input_state: dict[str, Any]
    criteria: list[str]
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    outputAssertions: dict[str, Any] = field(default_factory=dict)
    threshold: float = 0.7


@dataclass
class EvalResult:
    scenario: str
    score: float
    passed: bool
    reasoning: str
    latency_ms: float
    output: dict[str, Any]
    judge_model: str
    error: str | None = None


JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for an AI inventory management system.
You will receive:
1. The input state given to an agent node
2. The output produced by that node
3. A list of criteria to evaluate

Score the output on a scale of 0.0 to 1.0 based on the criteria.
Return ONLY a JSON object with this structure:
{
    "score": <float between 0.0 and 1.0>,
    "criteria_scores": {"<criterion>": <float>},
    "reasoning": "<brief explanation>"
}

Be strict: an output that hallucinates data, contradicts the input, or omits required fields scores low.
An output that correctly processes the input and meets all criteria scores 1.0.
Partial credit is given for mostly-correct outputs with minor issues."""


async def run_eval(
    scenario: EvalScenario,
    judge: LLMClient | None = None,
    runWithoutJudge: bool = False,
) -> EvalResult:
    start = time.monotonic()
    try:
        output = (
            await scenario.input_fn(scenario.input_state)
            if hasattr(scenario, "input_fn")
            else await scenario.node_fn(scenario.input_state)
        )
    except Exception as exc:
        return EvalResult(
            scenario=scenario.name,
            score=0.0,
            passed=False,
            reasoning=f"Node raised exception: {exc}",
            latency_ms=(time.monotonic() - start) * 1000,
            output={},
            judge_model="none",
            error=str(exc),
        )

    latency_ms = (time.monotonic() - start) * 1000

    if runWithoutJudge or judge is None:
        score = _heuristic_score(scenario, output)
        return EvalResult(
            scenario=scenario.name,
            score=score,
            passed=score >= scenario.threshold,
            reasoning="Heuristic evaluation (no judge LLM)",
            latency_ms=latency_ms,
            output=output,
            judge_model="heuristic",
        )

    judge_prompt = f"""Evaluate this agent node output against the criteria.

INPUT STATE:
{json.dumps(scenario.input_state, indent=2, default=str)}

OUTPUT:
{json.dumps(output, indent=2, default=str)}

CRITERIA:
{chr(10).join(f"- {c}" for c in scenario.criteria)}

Additional checks:
- Must contain: {scenario.must_contain or "none"}
- Must NOT contain: {scenario.must_not_contain or "none"}
- Output assertions: {json.dumps(scenario.outputAssertions, default=str) if scenario.outputAssertions else "none"}

Score this output. Return ONLY the JSON object."""

    try:
        result: LLMResult = await judge.call(judge_prompt)
        parsed = json.loads(result.text) if result.text else {}
        score = float(parsed.get("score", 0.0))
        reasoning = parsed.get("reasoning", "No reasoning provided")
    except Exception as exc:
        score = _heuristic_score(scenario, output)
        reasoning = f"Judge failed ({exc}), fell back to heuristic"
        result = LLMResult(text="", model="none")

    return EvalResult(
        scenario=scenario.name,
        score=min(max(score, 0.0), 1.0),
        passed=score >= scenario.threshold,
        reasoning=reasoning,
        latency_ms=latency_ms,
        output=output,
        judge_model=result.model if result else "heuristic",
    )


def _heuristic_score(scenario: EvalScenario, output: dict[str, Any]) -> float:
    score = 0.5
    for key in scenario.outputAssertions:
        if key in output:
            expected = scenario.outputAssertions[key]
            actual = output[key]
            if expected is True:
                score += 0.15
            elif expected is False and actual and actual != [] and actual != {}:
                score -= 0.15
            elif isinstance(expected, (int, float)) and actual is not None:
                score += 0.1
    for text in scenario.must_contain:
        output_text = json.dumps(output, default=str).lower()
        if text.lower() in output_text:
            score += 0.1
        else:
            score -= 0.15
    for text in scenario.must_not_contain:
        output_text = json.dumps(output, default=str).lower()
        if text.lower() in output_text:
            score -= 0.2
    return min(max(score, 0.0), 1.0)


async def run_eval_suite(
    scenarios: list[EvalScenario],
    judge: LLMClient | None = None,
    runWithoutJudge: bool = False,
) -> dict[str, Any]:
    results = []
    for scenario in scenarios:
        result = await run_eval(scenario, judge=judge, runWithoutJudge=runWithoutJudge)
        results.append(result)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    avg_score = sum(r.score for r in results) / total if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "avg_score": round(avg_score, 3),
        "results": [
            {
                "scenario": r.scenario,
                "score": r.score,
                "passed": r.passed,
                "reasoning": r.reasoning,
                "latency_ms": round(r.latency_ms, 1),
                "judge_model": r.judge_model,
                "error": r.error,
            }
            for r in results
        ],
    }
