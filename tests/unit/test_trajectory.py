import pytest

from verdict.evals.trajectory import check_trajectory
from verdict.models.trace_schemas import TraceFailureMode, TraceStep, TrajectoryExpectation


def call(i, tool, args=None, result="ok", error=None):
    return TraceStep(step_id=i, step_type="tool_call", tool_name=tool,
                     tool_arguments=args or {}, tool_result=result, error=error)


def answer(i, text):
    return TraceStep(step_id=i, step_type="final_answer", llm_output=text)


def checks(r):
    return [(f.check, f.severity) for f in r.findings]


def exp(**kw):
    return TrajectoryExpectation(**kw)


REFUND = [call(0, "lookup_order", {"order_id": "A1"}),
          call(1, "refund", {"order_id": "A1", "amount": 20}),
          answer(2, "Refunded $20 for order A1.")]


def test_clean_trajectory_passes_with_metrics():
    r = check_trajectory(REFUND, None, exp(tools=["lookup_order", "refund"]),
                         tools_available=["lookup_order", "refund"])
    assert r.passed and r.findings == []
    assert r.tool_sequence == ["lookup_order", "refund"]
    assert (r.n_steps, r.n_tool_calls, r.tool_recall, r.tool_precision) == (3, 2, 1.0, 1.0)


@pytest.mark.parametrize("match,expected,ok", [
    ("in_order", ["lookup_order", "refund"], True),
    ("in_order", ["refund", "lookup_order"], False),
    ("exact", ["lookup_order"], False),
    ("unordered", ["refund", "lookup_order"], True),
    ("unordered", ["refund", "refund"], False),
])
def test_sequence_match_modes(match, expected, ok):
    r = check_trajectory(REFUND, None, exp(tools=expected, match=match))
    assert r.passed is ok
    if not ok:
        f = r.findings[0]
        assert f.check == "tool_sequence" and f.failure_mode == TraceFailureMode.wrong_tool_selected
        assert "lookup_order → refund" in f.detail


def test_recall_and_precision_on_partial_match():
    steps = [call(0, "search"), call(1, "search"), call(2, "summarize"), answer(3, "Done.")]
    r = check_trajectory(steps, None, exp(tools=["search", "fetch", "summarize"]))
    assert r.tool_recall == pytest.approx(2 / 3)
    assert r.tool_precision == pytest.approx(2 / 3)


def test_forbidden_and_unknown_tools():
    steps = [call(0, "delete_account"), call(1, "teleport"), answer(2, "All done.")]
    r = check_trajectory(steps, None, exp(forbidden_tools=["delete_account"]),
                         tools_available=["delete_account", "lookup_order"])
    assert ("forbidden_tool", "error") in checks(r)
    unknown = [f for f in r.findings if f.check == "unknown_tool"]
    assert unknown[0].failure_mode == TraceFailureMode.hallucinated_tool_call
    assert "teleport" in unknown[0].detail


def test_argument_matchers():
    ok = exp(args=[
        {"tool": "refund", "args": {"order_id": "A1", "amount": 20}},
        {"tool": "lookup_order", "args": {"order_id": {"$regex": "^A\\d$"}}},
        {"tool": "refund", "args": {"order_id": {"$contains": "a1"}, "amount": {"$any": True}}},
    ])
    r = check_trajectory(REFUND, None, ok)
    assert r.passed and (r.args_matched, r.args_expected) == (3, 3)

    bad = exp(args=[{"tool": "refund", "args": {"amount": 200}},
                    {"tool": "escalate", "args": {"reason": {"$any": True}}}])
    r = check_trajectory(REFUND, None, bad)
    assert [f.check for f in r.findings] == ["tool_args", "tool_args"]
    assert '"amount": 20' in r.findings[0].detail and "never called" in r.findings[1].detail
    assert r.findings[0].failure_mode == TraceFailureMode.invalid_tool_arguments


def test_step_limits_and_output_contains():
    r = check_trajectory(REFUND, None, exp(max_tool_calls=1, max_steps=2,
                                           output_contains=["refunded", "receipt"]))
    assert checks(r) == [("max_tool_calls", "error"), ("max_steps", "error"),
                         ("output_contains", "error")]
    assert "'receipt'" in r.findings[-1].detail


def test_empty_output_and_agent_crash():
    r = check_trajectory([call(0, "search")], None, agent_error="RuntimeError: boom")
    assert checks(r) == [("agent_error", "error"), ("empty_output", "error")]
    r = check_trajectory([call(0, "search")], "   ")
    assert ("empty_output", "error") in checks(r)


def test_explicit_final_output_wins_over_final_answer_step():
    r = check_trajectory([answer(0, "")], "The answer is 4.")
    assert r.passed


@pytest.mark.parametrize("result,error", [
    ("Error: upstream timeout", None),
    ('{"error": "rate limited"}', None),
    ("HTTP 503 Service Unavailable", None),
    ("", "TimeoutError: 30s"),
])
def test_swallowed_tool_error_is_flagged(result, error):
    steps = [call(0, "get_weather", result=result, error=error),
             answer(1, "It's sunny and 22°C in Paris.")]
    r = check_trajectory(steps, None)
    assert checks(r) == [("error_swallowed", "error")]
    assert r.findings[0].failure_mode == TraceFailureMode.error_not_propagated


def test_tool_error_is_fine_when_acknowledged_or_recovered():
    failing = call(0, "get_weather", result="Error: upstream timeout")
    acknowledged = [failing, answer(1, "Sorry, the weather service is unavailable right now.")]
    assert check_trajectory(acknowledged, None).passed
    retried = [failing, call(1, "get_weather", result='{"temp": 22}'), answer(2, "22°C.")]
    assert check_trajectory(retried, None).passed


def test_ordinary_text_mentioning_errors_is_not_a_tool_error():
    steps = [call(0, "search", result="Common errors in Python include TypeError."),
             answer(1, "TypeError is common.")]
    assert check_trajectory(steps, None).passed


def test_empty_result_is_a_warning_unless_acknowledged():
    steps = [call(0, "search", result="[]"), answer(1, "The capital is Paris.")]
    r = check_trajectory(steps, None)
    assert r.passed and checks(r) == [("empty_result", "warning")]
    steps[-1] = answer(1, "The search returned no results.")
    assert check_trajectory(steps, None).findings == []


def test_repeated_identical_calls_warn():
    steps = [call(i, "search", {"q": "x"}) for i in range(3)] + [answer(3, "Found it.")]
    r = check_trajectory(steps, None)
    assert r.passed and checks(r) == [("repeated_call", "warning")]
    assert r.findings[0].failure_mode == TraceFailureMode.excessive_retries
    varied = [call(i, "search", {"q": str(i)}) for i in range(3)] + [answer(3, "Found it.")]
    assert check_trajectory(varied, None).findings == []
