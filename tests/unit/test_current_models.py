"""Compatibility with current Claude models.

Current models think by default (the first content block can be a thinking block)
and reject sampling parameters such as temperature with a 400.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from verdict.costs.pricing import get_model_pricing
from verdict.llm import message_text
from verdict.models.schemas import ExecutionResult, TestPrompt
from verdict.models.trace_schemas import AgentTrace, TraceStep

SAMPLING = {"temperature", "top_p", "top_k"}


def _msg(*blocks):
    return SimpleNamespace(content=list(blocks), usage=SimpleNamespace(input_tokens=10,
                                                                         output_tokens=5),
                           stop_reason="end_turn")


def _thinking():
    return SimpleNamespace(type="thinking", thinking="", signature="sig")


def _text(t):
    return SimpleNamespace(type="text", text=t)


def test_message_text_skips_thinking_and_tool_blocks():
    m = _msg(_thinking(), _text("hello "), SimpleNamespace(type="tool_use", name="x", input={}),
             _text("world"))
    assert message_text(m) == "hello world"
    assert message_text(_msg(_thinking())) == ""
    assert message_text(SimpleNamespace(content=[MagicMock(text="untyped mock")])) == "untyped mock"


@pytest.fixture
def api_key(monkeypatch):
    from verdict.config import settings
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    settings.get_settings.cache_clear()
    yield
    settings.get_settings.cache_clear()


def _client_returning(message):
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def test_judge_reads_text_after_thinking_and_sends_no_sampling_params(api_key):
    from verdict.agents import judge as judge_mod

    verdict_json = json.dumps({"passed": True, "score": 5, "failure_mode": None,
                               "reasoning": "The answer correctly states the refund window."})
    client = _client_returning(_msg(_thinking(), _text(verdict_json)))
    p = TestPrompt(id="a", prompt="q", expected_behavior="e", category="correctness",
                   severity="low")
    r = ExecutionResult(prompt_id="a", response="r", latency_ms=1)
    with patch.object(judge_mod.anthropic, "Anthropic", return_value=client):
        [j] = judge_mod.judge_results([p], [r], judge_models=["claude-sonnet-5-5"])
    assert j.passed and not j.metadata.get("judge_error")
    kwargs = client.messages.create.call_args.kwargs
    assert not SAMPLING & kwargs.keys() and kwargs["max_tokens"] >= 16000


def test_trace_judge_sends_no_sampling_params(api_key):
    from verdict.agents import trace_judge

    payload = json.dumps({"overall_passed": True, "overall_score": 5, "failure_modes": [],
                          "reasoning": "Every step used the right tool correctly.",
                          "step_judgments": []})
    client = _client_returning(_msg(_thinking(), _text(payload)))
    t = AgentTrace(agent_name="a", task="t", expected_behavior="e",
                   steps=[TraceStep(step_id=0, step_type="final_answer", llm_output="x")])
    with patch.object(trace_judge.anthropic, "Anthropic", return_value=client):
        [j] = trace_judge.judge_traces([t], judge_models=["claude-sonnet-5-5"])
    assert j.overall_passed
    assert not SAMPLING & client.messages.create.call_args.kwargs.keys()


def test_drafter_sends_no_sampling_params(api_key):
    from verdict.evals.trajectory import check_trajectory
    from verdict.traces import drafting

    out = json.dumps({"expected_behavior": "Refunds the order.", "category": "correctness",
                      "severity": "low", "notes": ""})
    client = _client_returning(_msg(_thinking(), _text(out)))
    t = AgentTrace(agent_name="a", task="Refund A1", expected_behavior="",
                   steps=[TraceStep(step_id=0, step_type="final_answer", llm_output="done")],
                   final_output="done")
    with patch("anthropic.Anthropic", return_value=client):
        draft = drafting.llm_drafter("claude-sonnet-5-5")
        result = draft(t, check_trajectory(t.steps, t.final_output))
    assert result["expected_behavior"] == "Refunds the order."
    assert not SAMPLING & client.messages.create.call_args.kwargs.keys()


@pytest.mark.parametrize("model,expected", [
    ("claude-opus-5-5", (4.00, 20.00)),
    ("claude-sonnet-5-5", (2.00, 10.00)),
    ("claude-haiku-5-5", (0.10, 0.50)),
    ("claude-opus-5", (5.00, 25.00)),
    ("claude-haiku-4-5-20251001", (1.00, 5.00)),  # dated id, prefix match
])
def test_pricing_for_current_models(model, expected):
    p = get_model_pricing(model)
    assert (p["input_per_1m_usd"], p["output_per_1m_usd"]) == expected


def test_default_models_are_current(api_key):
    from verdict.config.settings import get_settings

    s = get_settings()
    assert s.default_judge_model == "claude-sonnet-5-5"
    assert s.default_executor_model == "claude-haiku-5-5"
    assert all(get_model_pricing(m) for m in (s.default_generator_model, s.default_judge_model,
                                              s.default_reporter_model, s.default_executor_model))
