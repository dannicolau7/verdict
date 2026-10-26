import json

import pytest

from verdict.ci.comment import COMMENT_MARKER, render_json, render_markdown
from verdict.ci.config import GateConfig, StatsConfig
from verdict.ci.diff import DiffResult, GateResult, Outcome, analyze, judge_side
from verdict.models.schemas import ExecutionResult, Judgment, TestPrompt


def _case(cid: str) -> TestPrompt:
    return TestPrompt(
        id=cid, prompt=f"prompt {cid}", expected_behavior="does it", category="correctness",
        severity="medium",
    )


def _outcomes(case_id: str, passes: int, runs: int = 10, cost: float | None = 0.01,
              latency: float = 100.0) -> list[Outcome]:
    return [
        Outcome(
            case_id=case_id, run=i, passed=i < passes,
            reasoning="" if i < passes else f"{case_id} missed the policy",
            latency_ms=latency, cost_usd=cost,
        )
        for i in range(runs)
    ]


def _result(cases, base, head, gate=None, stats=None) -> DiffResult:
    suite, diffs, g = analyze(cases, base, head, gate or GateConfig(), stats or StatsConfig())
    return DiffResult(
        status="completed", base_ref="main", head_ref="HEAD", base_sha="a" * 40,
        head_sha="b" * 40, runs=10, stats_method=(stats or StatsConfig()).method,
        n_cases=len(cases), suite=suite, cases=diffs, gate=g,
    )


def test_no_change_passes_gate():
    cases = [_case("a"), _case("b")]
    base = _outcomes("a", 10) + _outcomes("b", 7)
    head = _outcomes("a", 10) + _outcomes("b", 7)
    r = _result(cases, base, head)
    assert r.gate.passed
    assert r.suite.delta == 0
    assert r.regressions == []
    assert [c.case_id for c in r.failing_on_head] == ["b"]


def test_significant_drop_breaches_gate_and_flags_case():
    cases = [_case(c) for c in "abcd"]
    base = [o for c in "abcd" for o in _outcomes(c, 10)]
    head = _outcomes("a", 2) + _outcomes("b", 10) + _outcomes("c", 10) + _outcomes("d", 10)
    r = _result(cases, base, head)
    assert not r.gate.passed
    assert [c.name for c in r.gate.breaches] == ["pass_rate"]
    assert [c.case_id for c in r.regressions] == ["a"]
    assert r.regressions[0].head_failures == ["a missed the policy"]


def test_small_noisy_drop_does_not_breach():
    cases = [_case("a")]
    r = _result(cases, _outcomes("a", 9), _outcomes("a", 8))
    assert r.suite.delta < -0.05
    assert r.suite.p_value > 0.05
    assert r.gate.passed
    assert r.cases[0].status == "unchanged"


def test_cost_gate():
    cases = [_case("a")]
    r = _result(
        cases, _outcomes("a", 10, cost=0.010), _outcomes("a", 10, cost=0.013),
        gate=GateConfig(cost_increase_max=0.2),
    )
    assert r.suite.cost_delta_pct > 0.2
    assert [c.name for c in r.gate.breaches] == ["cost"]


def test_cost_gate_skipped_when_unreported():
    cases = [_case("a")]
    r = _result(cases, _outcomes("a", 10, cost=None), _outcomes("a", 10, cost=None),
                gate=GateConfig(cost_increase_max=0.2))
    assert r.gate.passed
    assert "skipped" in r.gate.checks[-1].detail


def test_latency_and_case_regression_gates():
    cases = [_case(c) for c in "abcdefghij"]
    base = [o for c in "abcdefghij" for o in _outcomes(c, 10, latency=100)]
    head = _outcomes("a", 3, latency=150) + [
        o for c in "bcdefghij" for o in _outcomes(c, 10, latency=150)
    ]
    gate = GateConfig(
        max_pass_rate_drop=0.10, latency_increase_max=0.25, fail_on_case_regression=True
    )
    r = _result(cases, base, head, gate=gate)
    names = {c.name for c in r.gate.breaches}
    assert names == {"latency", "case_regressions"}  # suite drop is 7 pts, under the 10 pt max


def test_bootstrap_method():
    cases = [_case(c) for c in "abcd"]
    base = [o for c in "abcd" for o in _outcomes(c, 10)]
    head = [o for c in "abcd" for o in _outcomes(c, 5)]
    r = _result(cases, base, head, stats=StatsConfig(method="bootstrap"))
    assert not r.gate.passed
    assert r.suite.delta_ci_high is not None and r.suite.delta_ci_high < 0


def test_markdown_order_and_marker():
    cases = [_case(c) for c in "abcd"]
    base = [o for c in "abcd" for o in _outcomes(c, 10)]
    head = _outcomes("a", 2) + _outcomes("b", 9) + _outcomes("c", 10) + _outcomes("d", 10)
    md = render_markdown(_result(cases, base, head))
    assert md.startswith(COMMENT_MARKER)
    assert "❌ Verdict: regression detected" in md
    i_reg, i_fail, i_sum = md.index("#### Regressions"), md.index("#### Failing"), md.index("#### Summary")
    assert i_reg < i_fail < i_sum
    assert "| `a` | 10/10 | 2/10 |" in md
    assert "Cost / run" in md


def test_markdown_escapes_pipes():
    cases = [_case("a")]
    head = [Outcome(case_id="a", run=0, passed=False, reasoning="said a | b instead")]
    md = render_markdown(_result(cases, [Outcome(case_id="a", run=0, passed=True)], head))
    assert "a \\| b" in md


def test_skipped_render_and_json():
    r = DiffResult(status="skipped", base_ref="main", head_ref="HEAD", base_sha="a" * 40,
                   head_sha="b" * 40, runs=10, stats_method="fisher", gate=GateResult(passed=True))
    assert "skipped" in render_markdown(r)
    data = json.loads(render_json(r))
    assert data["status"] == "skipped" and data["gate"]["breaches"] == []


def test_judge_side_skips_errored_results():
    cases = [_case("a"), _case("b")]
    runs = [[
        ExecutionResult(prompt_id="a", response="ok", latency_ms=5),
        ExecutionResult(prompt_id="b", response="", latency_ms=5, error="TimeoutError: slow"),
    ]]
    judged: list[str] = []

    def judge(prompts, results):
        judged.extend(p.id for p in prompts)
        return [Judgment(prompt_id=p.id, passed=True, reasoning="Response meets the rubric.",
                         judge_model="fake") for p in prompts]

    out = judge_side(cases, runs, judge)
    assert judged == ["a"]
    assert [(o.case_id, o.passed, o.error) for o in out] == [
        ("a", True, None), ("b", False, "TimeoutError: slow"),
    ]


def test_consistency_stats_and_flaky_cases():
    cases = [_case("solid"), _case("flaky"), _case("broken")]
    base = _outcomes("solid", 10) + _outcomes("flaky", 10) + _outcomes("broken", 10)
    head = _outcomes("solid", 10) + _outcomes("flaky", 7) + _outcomes("broken", 0)
    r = _result(cases, base, head)
    by_id = {c.case_id: c for c in r.cases}
    assert by_id["flaky"].head.flaky and not by_id["solid"].head.flaky
    assert not by_id["broken"].head.flaky  # consistently failing is not flaky
    assert by_id["flaky"].head.pass_hat_k == {"10": 0.0}
    assert by_id["flaky"].head.pass_at_k == {"10": 1.0}
    assert r.suite.head.flaky_cases == 1 and r.suite.base.flaky_cases == 0
    assert r.suite.head.pass_hat_k["10"] == pytest.approx(1 / 3)
    assert [c.case_id for c in r.flaky_on_head] == ["flaky"]
    md = render_markdown(r)
    assert "| `flaky` | 7/10 flaky |" in md
    assert "| pass^10 (all 10 pass) | 100% | 33% |" in md
    assert "| Flaky cases | 0 | 1 | |" in md


def test_custom_k_values_skip_k_above_runs():
    cases = [_case("a")]
    r = _result(cases, _outcomes("a", 8), _outcomes("a", 8), stats=StatsConfig(k=[1, 3, 50]))
    assert set(r.cases[0].head.pass_hat_k) == {"1", "3"}
    assert r.cases[0].head.pass_hat_k["3"] == pytest.approx(56 / 120)


def test_power_warning_when_underpowered():
    cases = [_case(c) for c in "abcd"]
    base = [o for c in "abcd" for o in _outcomes(c, 9)]
    head = [o for c in "abcd" for o in _outcomes(c, 9)]
    r = _result(cases, base, head)  # 40 obs per side at 90% can't see a 5 pt drop
    power = [c for c in r.gate.checks if c.name == "power"]
    assert power and power[0].warning and not power[0].breached
    assert r.gate.passed
    assert r.suite.min_detectable_drop is None or r.suite.min_detectable_drop > 0.05
    assert "⚠️ underpowered" in render_markdown(r)


def test_no_power_warning_when_suite_is_big_enough():
    ids = [f"c{i}" for i in range(80)]
    cases = [_case(c) for c in ids]
    base = [o for c in ids for o in _outcomes(c, 9)]
    r = _result(cases, base, base, gate=GateConfig(max_pass_rate_drop=0.10))
    assert r.suite.min_detectable_drop < 0.10
    assert not any(c.name == "power" for c in r.gate.checks)
