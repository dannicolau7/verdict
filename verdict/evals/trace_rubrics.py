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
Pass: The correct tool was selected (or the correct LLM inference was made), arguments
  are valid and well-formed, the output was correctly consumed in the next step, and
  any error was handled appropriately.

Fail: Any of the following applies:
  - Wrong tool selected for the current sub-task
  - Tool arguments are malformed, missing required fields, or hallucinated
  - A tool error occurred and was not handled or propagated
  - The agent skipped a required step without justification
  - The step's output was misread or ignored in the following step"""
