import json

import pytest
from click.testing import CliRunner

from verdict.ci.comment import TRAJECTORY_MARKER, render_markdown, render_trajectory_markdown
from verdict.ci.config import GateConfig, StatsConfig
from verdict.ci.diff import DiffResult, analyze, judge_side
from verdict.ci.suite import SuiteError, load_suite
from verdict.ci.trajectory import evaluate_traces
from verdict.cli import main
from verdict.models.schemas import ExecutionResult, Judgment, TestPrompt
from verdict.models.trace_schemas import AgentTrace, TraceStep

EXPECT = {"tools": ["lookup_order", "refund"], "forbidden_tools": ["delete_account"]}


def _case(cid="refund", expectation=EXPECT):
    meta = {"expected_trajectory": expectation} if expectation else {}
    return TestPrompt(id=cid, prompt="Refund order A1", expected_behavior="refunds A1",
                      category="correctness", severity="high", metadata=meta)


def _steps(*tools, answer="Refunded order A1."):
    steps = [TraceStep(step_id=i, step_type="tool_call", tool_name=t, tool_arguments={},
                       tool_result="ok") for i, t in enumerate(tools)]
    return steps + [TraceStep(step_id=len(tools), step_type="final_answer", llm_output=answer)]


def _result(cid, steps, response="Refunded order A1."):
    return ExecutionResult(prompt_id=cid, response=response, latency_ms=5, steps=steps)


class CountingJudge:
    def __init__(self):
        self.calls = 0

    def __call__(self, prompts, results):
        self.calls += len(prompts)
        return [Judgment(prompt_id=p.id, passed=True, judge_model="fake",
                         reasoning="Looks like a correct refund response.") for p in prompts]


def test_suite_validates_expected_trajectory(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text(json.dumps({"id": "a", "prompt": "p", "expected_behavior": "e",
                             "expected_trajectory": EXPECT}) + "\n")
    assert load_suite(f)[0].metadata["expected_trajectory"]["tools"] == ["lookup_order", "refund"]
    f.write_text(json.dumps({"id": "a", "prompt": "p", "expected_behavior": "e",
                             "expected_trajectory": {"tools": "refund", "bogus": 1}}) + "\n")
    with pytest.raises(SuiteError, match="expected_trajectory"):
        load_suite(f)


def test_trajectory_failure_skips_judge_and_explains():
    judge = CountingJudge()
    runs = [[_result("refund", _steps("lookup_order", "delete_account", "refund"))]]
    [o] = judge_side([_case()], runs, judge)
    assert judge.calls == 0
    assert not o.passed
    assert o.reasoning == "trajectory: called forbidden tool `delete_account`"
    assert o.failure_mode == "wrong_tool_selected"
    assert (o.n_steps, o.n_tool_calls) == (4, 3)


def test_passing_trajectory_still_goes_to_the_judge():
    judge = CountingJudge()
    [o] = judge_side([_case()], [[_result("refund", _steps("lookup_order", "refund"))]], judge)
    assert judge.calls == 1 and o.passed and o.trajectory_errors == []


def test_expectation_without_reported_steps_fails():
    judge = CountingJudge()
    res = ExecutionResult(prompt_id="refund", response="Refunded.", latency_ms=5)
    [o] = judge_side([_case()], [[res]], judge)
    assert not o.passed and "reported no steps" in o.reasoning and o.n_steps is None


def test_no_steps_no_expectation_is_unchanged_behaviour():
    judge = CountingJudge()
    res = ExecutionResult(prompt_id="refund", response="Refunded.", latency_ms=5)
    [o] = judge_side([_case(expectation=None)], [[res]], judge)
    assert o.passed and o.n_steps is None and judge.calls == 1


def test_degradation_checks_run_without_expectation():
    judge = CountingJudge()
    steps = [TraceStep(step_id=0, step_type="tool_call", tool_name="get_order",
                       tool_result="Error: database timeout"),
             TraceStep(step_id=1, step_type="final_answer", llm_output="Your order shipped.")]
    [o] = judge_side([_case(expectation=None)], [[_result("refund", steps, "Your order shipped.")]],
                     judge)
    assert not o.passed and "doesn't say so" in o.reasoning and judge.calls == 0


def _diff(cases, base, head, gate=None):
    suite, diffs, g = analyze(cases, base, head, gate or GateConfig(), StatsConfig())
    return DiffResult(status="completed", base_ref="main", head_ref="HEAD", base_sha="a" * 40,
                      head_sha="b" * 40, runs=4, stats_method="fisher", n_cases=len(cases),
                      suite=suite, cases=diffs, gate=g)


def test_step_stats_gate_and_comment_rows():
    judge = CountingJudge()
    case = _case(expectation={"tools": ["lookup_order", "refund"]})
    base = judge_side([case], [[_result("refund", _steps("lookup_order", "refund"))]] * 4, judge)
    head = judge_side([case], [[_result("refund", _steps("lookup_order", "lookup_order",
                                                         "lookup_order", "refund"))]] * 4, judge)
    r = _diff([case], base, head, gate=GateConfig(steps_increase_max=0.25))
    assert (r.suite.base.mean_tool_calls, r.suite.head.mean_tool_calls) == (2.0, 4.0)
    assert r.suite.steps_delta_pct == pytest.approx(2 / 3)
    assert "steps" in [c.name for c in r.gate.breaches]
    md = render_markdown(r)
    assert "| Tool calls / run | 2.0 | 4.0 | +2.0 |" in md
    assert "| Steps / run | 3.0 | 5.0 | +66.7% |" in md


def test_trajectory_failures_row():
    judge = CountingJudge()
    case = _case()
    base = judge_side([case], [[_result("refund", _steps("lookup_order", "refund"))]] * 4, judge)
    head = judge_side([case], [[_result("refund", _steps("delete_account"))]] * 4, judge)
    md = render_markdown(_diff([case], base, head))
    assert "| Trajectory failures | 0 | 4 | |" in md
    assert "trajectory: expected lookup_order → refund" in md


# --- verdict trajectory -----------------------------------------------------


def _trace(tid, tools, expectation=None, answer="Refunded order A1."):
    return AgentTrace(trace_id=tid, agent_name="support-bot", task="Refund A1",
                      expected_behavior="refunds A1", tools_available=["lookup_order", "refund"],
                      steps=_steps(*tools, answer=answer), final_output=answer,
                      expected_trajectory=expectation)


def test_evaluate_traces_and_render():
    traces = [
        _trace("good", ["lookup_order", "refund"], {"tools": ["lookup_order", "refund"]}),
        _trace("bad", ["refund"], {"tools": ["lookup_order", "refund"]}),
        _trace("loose", ["lookup_order", "teleport", "refund"]),
    ]
    rep = evaluate_traces(traces, min_pass_rate=0.5)
    assert (rep.n_traces, rep.n_passed) == (3, 1) and not rep.passed
    assert rep.finding_counts == {"tool_sequence": 1, "unknown_tool": 1}
    assert rep.mean_tool_recall == pytest.approx(0.75)
    md = render_trajectory_markdown(rep)
    assert md.startswith(TRAJECTORY_MARKER) and "1/3 pass" in md
    assert "| `bad` | expected lookup_order → refund (in order), got refund |" in md


def test_trajectory_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "traces"
    d.mkdir()
    for t in (_trace("t1", ["lookup_order", "refund"]), _trace("t2", ["lookup_order", "refund"])):
        (d / f"{t.trace_id}.json").write_text(t.model_dump_json())
    ok = CliRunner().invoke(main, ["trajectory", "--traces-dir", str(d)], catch_exceptions=False)
    assert ok.exit_code == 0, ok.output
    assert json.loads((tmp_path / "verdict-trajectory.json").read_text())["n_passed"] == 2

    bad = _trace("t3", ["refund"], {"tools": ["lookup_order", "refund"]})
    (d / "t3.json").write_text(bad.model_dump_json())
    r = CliRunner().invoke(main, ["trajectory", "--traces-dir", str(d), "--min-pass-rate", "0.9"],
                           catch_exceptions=False)
    assert r.exit_code == 2, r.output
    r = CliRunner().invoke(main, ["trajectory"])
    assert r.exit_code == 2 and "exactly one" in r.output
