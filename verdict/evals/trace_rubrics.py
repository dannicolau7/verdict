"""Rubrics for the trace judge.

OVERALL_RUBRIC: Holistic 1-5 graded rubric for the full agent trace.
STEP_RUBRIC:    Binary pass/fail guidance for each individual step.
"""

from __future__ import annotations

OVERALL_RUBRIC: str = """\
Score 5 — Excellent: All steps are valid, the task is fully completed, no unnecessary
  or redundant steps, all errors handled gracefully.

Score 4 — Good: Task is completed successfully with one minor inefficiency (e.g.,
  one sub-optimal tool choice or a slightly verbose step), but no correctness issue.

Score 3 — Partial: Task is partially completed OR the agent made 1-2 wrong tool
  selections, OR there is a non-critical error that was eventually recovered.

Score 2 — Poor: Task is not completed, OR the agent repeated invalid steps without
  recovering, OR a critical tool failed and was ignored, OR the agent gave up early.

Score 1 — Failure: Agent crashed with an unhandled exception, OR hallucinated a tool
  call to a non-existent tool, OR produced output that is factually wrong / harmful."""

STEP_RUBRIC: str = """\
Evaluate each step according to its type. Apply ONLY the criteria for that step's type.

tool_call steps — judge on:
  Pass: Correct tool selected for the current sub-task; arguments are valid, well-formed,
    and not hallucinated; no required fields are missing.
  Fail: Wrong tool selected; arguments malformed, missing required fields, or invented;
    tool does not exist (hallucinated_tool_call).

tool_result / observation steps — judge on:
  Pass: The result or observation was correctly consumed in the following step; if an
    error was returned (error field set, or result contains explicit error text such as
    exception messages, {"error": "…"}, or HTTP 4xx/5xx status), it was handled or
    propagated appropriately.
  Fail — two independent criteria:
    (1) Output misread: the result's meaning was inverted or misunderstood in the next
        step. This applies to ALL tool_result steps.
    (2) Error ignored (error_not_propagated / unhandled_error): ONLY applicable when
        the step has an error field set OR the result field explicitly contains an error
        message. A step whose result field contains valid, successful data — even if the
        agent subsequently makes a wrong decision — MUST NOT receive error_not_propagated
        or unhandled_error. Assign wrong_tool_selected or task_not_completed instead.

llm_call steps — judge on:
  Pass: The inference is appropriate for the current task context; no hallucinated facts
    are introduced; the decision is consistent with information available at that point.
  Fail: The LLM introduces false information; contradicts earlier established facts;
    or reaches a conclusion unsupported by the context.

final_answer steps — judge on:
  Pass: The task goal is fully addressed; the answer is accurate, complete, and consistent
    with the trace evidence; no hallucinated claims.
  Fail: Task not completed; answer contradicts trace evidence; key information is missing;
    claims are fabricated.

If the step type is not one of the above, apply the llm_call criteria."""
