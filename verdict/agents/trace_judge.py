"""Trace judge for agent-trace evaluation (Phase 2 / v0.3.0).

Design priorities (mirrors judge.py):
1. Prompt injection resistance — step content wrapped in <trace_step> XML tags.
2. Consistency — temperature 0.1.
3. Graceful degradation — error default on parse failure.
4. Multi-judge support — majority vote on overall_passed, averaged scores.
"""

from __future__ import annotations

import json
import logging
import re

import anthropic

from verdict.agents.prompts.trace_judge_prompt import SYSTEM_PROMPT, TRACE_JUDGMENT_TEMPLATE
from verdict.config.settings import get_settings
from verdict.evals.trace_rubrics import OVERALL_RUBRIC, STEP_RUBRIC
from verdict.models.trace_schemas import (
    AgentTrace,
    StepJudgment,
    TraceFailureMode,
    TraceJudgment,
    TraceStep,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


_CLOSE_TAG = "</trace_step>"
_CLOSE_TAG_ESCAPED = "<\\/trace_step>"


def _sanitise(s: str) -> str:
    """Prevent user-controlled strings from closing the <trace_step> XML wrapper."""
    return s.replace(_CLOSE_TAG, _CLOSE_TAG_ESCAPED)


def _format_steps(steps: list[TraceStep]) -> str:
    """Render steps as injection-safe XML-tagged blocks.

    User-controlled fields (tool_result, llm_input, llm_output, error) are
    sanitised so that a payload containing </trace_step> cannot escape the
    wrapper and appear as free text in the prompt.
    """
    parts: list[str] = []
    for step in steps:
        lines = [f"<trace_step id={step.step_id} type={step.step_type}>"]
        if step.tool_name:
            lines.append(f"  tool: {step.tool_name}")
        if step.tool_arguments:
            lines.append(f"  arguments: {json.dumps(step.tool_arguments)}")
        if step.tool_result is not None:
            lines.append(f"  result: {_sanitise(step.tool_result)}")
        if step.llm_input:
            lines.append(f"  llm_input: {_sanitise(step.llm_input)}")
        if step.llm_output:
            lines.append(f"  llm_output: {_sanitise(step.llm_output)}")
        if step.error:
            lines.append(f"  error: {_sanitise(step.error)}")
        if step.latency_ms is not None:
            lines.append(f"  latency_ms: {step.latency_ms}")
        lines.append(_CLOSE_TAG)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found (first 300 chars): {text[:300]!r}")
    return json.loads(text[start : end + 1])


def _judge_one_trace(
    client: anthropic.Anthropic,
    model: str,
    trace: AgentTrace,
) -> dict:
    """Call the trace judge LLM for one AgentTrace. Retries once on parse failure."""
    formatted = _format_steps(trace.steps)
    user_msg = TRACE_JUDGMENT_TEMPLATE.format(
        agent_name=trace.agent_name,
        task=trace.task,
        expected_behavior=trace.expected_behavior,
        tools_available=", ".join(trace.tools_available) or "(none specified)",
        overall_rubric=OVERALL_RUBRIC,
        step_rubric=STEP_RUBRIC,
        formatted_steps=formatted,
    )

    valid_failure_modes = {m.value for m in TraceFailureMode}

    for attempt in range(2):
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0.1,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text: str = message.content[0].text  # type: ignore[index]

        try:
            data = _extract_json_object(raw_text)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("Attempt %d: JSON parse failed: %s", attempt + 1, exc)
            if attempt == 0:
                user_msg = (
                    user_msg
                    + "\n\nYour previous response could not be parsed as JSON. "
                    "Return ONLY a JSON object, nothing else. Start with { and end with }."
                )
            continue

        # Sanitize failure_modes list
        raw_fms = data.get("failure_modes", [])
        data["failure_modes"] = [
            fm for fm in (raw_fms if isinstance(raw_fms, list) else [])
            if fm in valid_failure_modes
        ]

        # Sanitize step_judgments
        for sj in data.get("step_judgments", []):
            fm = sj.get("failure_mode")
            if fm is not None and fm not in valid_failure_modes:
                sj["failure_mode"] = "other"
            score = sj.get("score")
            if score is not None:
                try:
                    si = int(score)
                    sj["score"] = si if 1 <= si <= 5 else None
                except (ValueError, TypeError):
                    sj["score"] = None

        # Guard: error-propagation failure modes require a real error in the step.
        # Steps where TraceStep.error is None cannot trigger error_not_propagated or
        # unhandled_error regardless of what the LLM returned.
        _error_step_ids = {s.step_id for s in trace.steps if s.error is not None}
        _error_only_modes = {"error_not_propagated", "unhandled_error"}
        for sj in data.get("step_judgments", []):
            if sj.get("failure_mode") in _error_only_modes:
                if sj.get("step_id") not in _error_step_ids:
                    sj["failure_mode"] = None
                    sj["passed"] = True
        # Prune top-level failure_modes list: remove error-propagation modes that no
        # longer appear in any step judgment (i.e. all occurrences were stripped above).
        _surviving_step_modes = {
            sj.get("failure_mode")
            for sj in data.get("step_judgments", [])
            if sj.get("failure_mode") is not None
        }
        data["failure_modes"] = [
            fm for fm in data.get("failure_modes", [])
            if fm not in _error_only_modes or fm in _surviving_step_modes
        ]

        # Sanitize overall_score
        os_ = data.get("overall_score")
        if os_ is not None:
            try:
                osi = int(os_)
                data["overall_score"] = osi if 1 <= osi <= 5 else None
            except (ValueError, TypeError):
                data["overall_score"] = None

        data["_model"] = model
        return data

    raise RuntimeError(f"Trace judge failed after 2 attempts for trace_id={trace.trace_id}")


def _make_error_trace_judgment(trace_id: str, model: str, reason: str) -> TraceJudgment:
    """Return a safe-default failed TraceJudgment when the judge errors."""
    msg = f"Trace judge failed: {reason}"
    return TraceJudgment(
        trace_id=trace_id,
        overall_passed=False,
        overall_score=None,
        reasoning=msg if len(msg) >= 20 else msg + " (judge error)",
        step_judgments=[],
        failure_modes=[TraceFailureMode.other],
        judge_model=model,
        metadata={"judge_error": True},
    )


# ---------------------------------------------------------------------------
# Multi-judge helpers (parallel to judge.py)
# ---------------------------------------------------------------------------


def _majority_passed(results: list[dict]) -> bool:
    votes = [bool(r.get("overall_passed")) for r in results]
    return sum(votes) > len(votes) / 2


def _average_score(results: list[dict]) -> int | None:
    scores = [r.get("overall_score") for r in results if r.get("overall_score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores))


def _agreement_rate(results: list[dict]) -> float:
    if len(results) < 2:
        return 1.0
    votes = [bool(r.get("overall_passed")) for r in results]
    majority = _majority_passed(results)
    return sum(v == majority for v in votes) / len(votes)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def judge_trace(
    trace: AgentTrace,
    judge_models: list[str] | None = None,
) -> TraceJudgment:
    """Judge a single AgentTrace. Convenience wrapper around judge_traces."""
    return judge_traces([trace], judge_models=judge_models)[0]


def judge_traces(
    traces: list[AgentTrace],
    judge_models: list[str] | None = None,
) -> list[TraceJudgment]:
    """Evaluate each AgentTrace using the trace judge LLM.

    Args:
        traces:       List of AgentTrace objects to evaluate.
        judge_models: Model IDs for multi-judge mode. If None, uses
                      settings.default_judge_model.

    Returns:
        list[TraceJudgment] in the same order as traces.
        On failure, a safe-default failed TraceJudgment is returned so no
        trace is silently dropped.
    """
    settings = get_settings()
    primary_model = settings.default_judge_model

    resolved_models = judge_models if judge_models else [primary_model]
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    judgments: list[TraceJudgment] = []

    for trace in traces:
        if len(resolved_models) == 1:
            model = resolved_models[0]
            try:
                raw = _judge_one_trace(client, model, trace)
            except Exception as exc:
                logger.error("Trace judge failed for trace_id=%s: %s", trace.trace_id, exc)
                judgments.append(_make_error_trace_judgment(trace.trace_id, model, str(exc)))
                continue

            try:
                step_judgments = [
                    StepJudgment(
                        step_id=sj["step_id"],
                        passed=bool(sj.get("passed", False)),
                        score=sj.get("score"),
                        reasoning=sj.get("reasoning", "No step reasoning provided."),
                        failure_mode=(
                            TraceFailureMode(sj["failure_mode"])
                            if sj.get("failure_mode")
                            else None
                        ),
                    )
                    for sj in raw.get("step_judgments", [])
                ]
                failure_modes = [
                    TraceFailureMode(fm)
                    for fm in raw.get("failure_modes", [])
                    if fm in {m.value for m in TraceFailureMode}
                ]
                judgments.append(
                    TraceJudgment(
                        trace_id=trace.trace_id,
                        overall_passed=bool(raw.get("overall_passed", False)),
                        overall_score=raw.get("overall_score"),
                        reasoning=raw.get("reasoning", "No reasoning provided by judge."),
                        step_judgments=step_judgments,
                        failure_modes=failure_modes,
                        judge_model=model,
                        metadata={},
                    )
                )
            except Exception as exc:
                logger.error(
                    "TraceJudgment validation failed for trace_id=%s: %s", trace.trace_id, exc
                )
                judgments.append(_make_error_trace_judgment(trace.trace_id, model, str(exc)))

        else:
            # Multi-judge path
            per_judge: list[dict] = []
            for model in resolved_models:
                try:
                    per_judge.append(_judge_one_trace(client, model, trace))
                except Exception as exc:
                    logger.warning(
                        "Judge %r failed for trace_id=%s: %s", model, trace.trace_id, exc
                    )
                    per_judge.append(
                        {"overall_passed": False, "overall_score": None,
                         "reasoning": str(exc), "failure_modes": ["other"],
                         "step_judgments": []}
                    )

            passed = _majority_passed(per_judge)
            score = _average_score(per_judge)
            agreement = _agreement_rate(per_judge)
            primary_raw = per_judge[0]

            # Merge failure modes across all judges (union)
            all_fm_strs: set[str] = set()
            for r in per_judge:
                all_fm_strs.update(r.get("failure_modes", []))
            valid_fms = {m.value for m in TraceFailureMode}
            failure_modes = [TraceFailureMode(fm) for fm in all_fm_strs if fm in valid_fms]

            try:
                step_judgments = [
                    StepJudgment(
                        step_id=sj["step_id"],
                        passed=bool(sj.get("passed", False)),
                        score=sj.get("score"),
                        reasoning=sj.get("reasoning", "Multi-judge step assessment."),
                        failure_mode=(
                            TraceFailureMode(sj["failure_mode"])
                            if sj.get("failure_mode")
                            else None
                        ),
                    )
                    for sj in primary_raw.get("step_judgments", [])
                ]
                judgments.append(
                    TraceJudgment(
                        trace_id=trace.trace_id,
                        overall_passed=passed,
                        overall_score=score,
                        reasoning=primary_raw.get("reasoning", "Multi-judge consensus."),
                        step_judgments=step_judgments,
                        failure_modes=failure_modes,
                        judge_model=resolved_models[0],
                        metadata={
                            "multi_judge": True,
                            "judge_models": resolved_models,
                            "agreement_rate": agreement,
                        },
                    )
                )
            except Exception as exc:
                logger.error(
                    "Multi-judge TraceJudgment failed for trace_id=%s: %s", trace.trace_id, exc
                )
                judgments.append(
                    _make_error_trace_judgment(trace.trace_id, resolved_models[0], str(exc))
                )

    return judgments
