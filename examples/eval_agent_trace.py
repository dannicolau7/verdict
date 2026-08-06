"""Agent-trace evaluation — worked example (Phase 2 / v0.3.0).

Demonstrates loading AgentTrace data, judging traces, and building a
TraceEvalReport without requiring a real agent.

If ANTHROPIC_API_KEY is set, calls the trace judge LLM. Otherwise, uses
synthetic TraceJudgment objects so the builder/report path can be exercised
offline.

Run from the repo root:
    python examples/eval_agent_trace.py
    python examples/eval_agent_trace.py --output-dir /tmp/my-trace-demo
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic traces
# ---------------------------------------------------------------------------

def _synthetic_traces() -> list[dict]:
    """Two synthetic AgentTraces — one successful, one with a deliberate failure."""
    return [
        {
            "trace_id": "aaaabbbb-0000-0000-0000-000000000001",
            "agent_name": "research-agent-v1",
            "task": "Find recent papers on retrieval-augmented generation and summarize findings.",
            "expected_behavior": (
                "Agent should call web_search with a specific query about RAG papers, "
                "retrieve results, then call summarize_text with the retrieved content, "
                "and return a concise summary."
            ),
            "tools_available": ["web_search", "summarize_text", "fetch_url"],
            "steps": [
                {
                    "step_id": 0,
                    "step_type": "llm_call",
                    "llm_input": "Find recent papers on retrieval-augmented generation.",
                    "llm_output": "I will search for RAG papers using web_search.",
                    "latency_ms": 320.0,
                },
                {
                    "step_id": 1,
                    "step_type": "tool_call",
                    "tool_name": "web_search",
                    "tool_arguments": {"query": "retrieval-augmented generation papers 2024 2025"},
                    "latency_ms": 780.0,
                },
                {
                    "step_id": 2,
                    "step_type": "tool_result",
                    "tool_result": (
                        "1. RAG-Fusion (2024) — combines multiple queries...\n"
                        "2. IterRAG (2025) — iterative retrieval approach...\n"
                        "3. RAPTOR (2024) — recursive abstractive processing..."
                    ),
                    "latency_ms": 45.0,
                },
                {
                    "step_id": 3,
                    "step_type": "tool_call",
                    "tool_name": "summarize_text",
                    "tool_arguments": {
                        "text": "RAG-Fusion, IterRAG, RAPTOR...",
                        "max_words": 100,
                    },
                    "latency_ms": 540.0,
                },
                {
                    "step_id": 4,
                    "step_type": "final_answer",
                    "llm_output": (
                        "Recent RAG advances include RAG-Fusion (multi-query fusion), "
                        "IterRAG (iterative retrieval), and RAPTOR (recursive summarization). "
                        "These approaches improve factual grounding over naive RAG baselines."
                    ),
                    "latency_ms": 290.0,
                },
            ],
            "final_output": (
                "Recent RAG advances include RAG-Fusion, IterRAG, and RAPTOR, "
                "each improving factual grounding through different retrieval strategies."
            ),
            "total_latency_ms": 1975.0,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "trace_id": "ccccdddd-0000-0000-0000-000000000002",
            "agent_name": "research-agent-v1",
            "task": "Fetch the abstract of the RAPTOR paper from arxiv.",
            "expected_behavior": (
                "Agent should call fetch_url with the arxiv RAPTOR paper URL "
                "and return the abstract text."
            ),
            "tools_available": ["web_search", "summarize_text", "fetch_url"],
            "steps": [
                {
                    "step_id": 0,
                    "step_type": "llm_call",
                    "llm_input": "Fetch the abstract of the RAPTOR paper from arxiv.",
                    "llm_output": "I will search for it first.",
                    "latency_ms": 310.0,
                },
                {
                    "step_id": 1,
                    "step_type": "tool_call",
                    "tool_name": "web_search",
                    # Deliberate failure: should have used fetch_url with a known URL
                    "tool_arguments": {"query": "RAPTOR paper"},
                    "latency_ms": 810.0,
                },
                {
                    "step_id": 2,
                    "step_type": "tool_result",
                    "tool_result": "No direct URL found.",
                    "latency_ms": 30.0,
                },
                {
                    "step_id": 3,
                    "step_type": "final_answer",
                    "llm_output": "I was unable to retrieve the abstract.",
                    "latency_ms": 200.0,
                },
            ],
            "final_output": "I was unable to retrieve the abstract.",
            "total_latency_ms": 1350.0,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]


def _synthetic_judgments(traces: list) -> list:
    """Return synthetic TraceJudgments without calling the LLM."""
    from verdict.models.trace_schemas import StepJudgment, TraceFailureMode, TraceJudgment

    results = []
    for i, trace in enumerate(traces):
        if i == 0:
            results.append(
                TraceJudgment(
                    trace_id=trace.trace_id,
                    overall_passed=True,
                    overall_score=5,
                    reasoning=(
                        "The agent correctly selected web_search with a specific query, "
                        "retrieved results, called summarize_text on the content, and "
                        "produced a coherent final answer. All steps are valid and efficient."
                    ),
                    step_judgments=[
                        StepJudgment(
                            step_id=0, passed=True, score=None,
                            reasoning="LLM correctly planned to use web_search.",
                        ),
                        StepJudgment(
                            step_id=1, passed=True, score=None,
                            reasoning="web_search called with an appropriately specific query.",
                        ),
                        StepJudgment(
                            step_id=2, passed=True, score=None,
                            reasoning="Tool result consumed and passed to next step.",
                        ),
                        StepJudgment(
                            step_id=3, passed=True, score=None,
                            reasoning="summarize_text called with correct arguments.",
                        ),
                        StepJudgment(
                            step_id=4, passed=True, score=None,
                            reasoning="Final answer is accurate and concise.",
                        ),
                    ],
                    failure_modes=[],
                    judge_model="synthetic",
                )
            )
        else:
            results.append(
                TraceJudgment(
                    trace_id=trace.trace_id,
                    overall_passed=False,
                    overall_score=2,
                    reasoning=(
                        "The agent should have called fetch_url with the known arxiv URL "
                        "directly. Instead it used web_search which returned no useful result, "
                        "and then gave up without retrying with fetch_url. Task not completed."
                    ),
                    step_judgments=[
                        StepJudgment(
                            step_id=0, passed=True, score=None,
                            reasoning="LLM correctly identified the task.",
                        ),
                        StepJudgment(
                            step_id=1, passed=False, score=None,
                            reasoning=(
                                "Should have called fetch_url with the arxiv URL, "
                                "not web_search with a vague query."
                            ),
                            failure_mode=TraceFailureMode.wrong_tool_selected,
                        ),
                        StepJudgment(
                            step_id=2, passed=True, score=None,
                            reasoning="Tool result correctly received.",
                        ),
                        StepJudgment(
                            step_id=3, passed=False, score=None,
                            reasoning="Agent gave up without attempting fetch_url as a fallback.",
                            failure_mode=TraceFailureMode.task_not_completed,
                        ),
                    ],
                    failure_modes=[
                        TraceFailureMode.wrong_tool_selected,
                        TraceFailureMode.task_not_completed,
                    ],
                    judge_model="synthetic",
                )
            )
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Agent-trace evaluation example")
    parser.add_argument("--output-dir", default="/tmp/verdict-trace-demo")
    args = parser.parse_args()

    # Write synthetic traces to a temp file and load them back through ingestor
    import tempfile

    from verdict.adapters.trace_ingestor import load_traces
    from verdict.reports.trace_builder import build_trace_eval_markdown, build_trace_eval_report
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_synthetic_traces(), f, indent=2)
        tmp_path = Path(f.name)

    traces = load_traces(tmp_path)
    tmp_path.unlink(missing_ok=True)

    print(f"Loaded {len(traces)} traces for agent: {traces[0].agent_name}")
    print()

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_api_key:
        from verdict.agents.trace_judge import judge_traces
        print("ANTHROPIC_API_KEY found — running LLM trace judge…")
        judgments = judge_traces(traces)
    else:
        print("No ANTHROPIC_API_KEY — using synthetic judgments (builder/report demo only).")
        judgments = _synthetic_judgments(traces)

    report = build_trace_eval_report(judgments, agent_name=traces[0].agent_name)

    print(f"Pass rate: {report.pass_rate:.1%}  ({sum(1 for j in judgments if j.overall_passed)}/{report.total_traces})")
    if report.pass_rate_ci_low is not None:
        print(f"95% CI:   {report.pass_rate_ci_low:.1%} – {report.pass_rate_ci_high:.1%}")
    print()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"trace_eval_{report.run_id[:8]}.json"
    md_path = out_dir / f"trace_eval_{report.run_id[:8]}.md"

    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    md_path.write_text(build_trace_eval_markdown(report), encoding="utf-8")

    print(f"JSON report : {json_path}")
    print(f"Markdown    : {md_path}")
    print()
    print("Failure modes observed:")
    for fm, count in sorted(report.failure_mode_counts.items(), key=lambda x: -x[1]):
        print(f"  {fm}: {count}")


if __name__ == "__main__":
    main()
