import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from support_agent import run_agent
from support_agent.agent import MAX_TURNS, system_prompt
from support_agent.tools import ToolBox, load_data, load_tool_definitions

ROOT = Path(__file__).resolve().parent.parent


def test_refund_flow_records_trajectory(h):
    client = h.FakeClient(
        h.reply(h.thinking(), h.tool_use("t1", "lookup_order", order_id="TS-1001")),
        h.reply(h.tool_use("t2", "refund", order_id="TS-1001", amount=89.0, reason="leaks")),
        h.reply(h.thinking(), h.text("Refunded $89.00 for TS-1001.")),
    )
    box = ToolBox()
    run = run_agent("ana@example.com: refund TS-1001", client=client, model="m", effort="low",
                    toolbox=box)
    assert run.error is None and run.answer == "Refunded $89.00 for TS-1001."
    assert [s.get("tool", s["type"]) for s in run.steps] == ["lookup_order", "refund", "final_answer"]
    assert box.refunds == [{"order_id": "TS-1001", "amount": 89.0, "reason": "leaks"}]
    assert (run.input_tokens, run.output_tokens) == (3000, 300)

    first = client.calls[0]
    assert first["model"] == "m" and first["output_config"] == {"effort": "low"}
    assert not {"temperature", "top_p", "top_k"} & first.keys()
    assert [t["name"] for t in first["tools"]] == ["escalate", "lookup_order", "refund"]
    # the full assistant turn (thinking included) goes back, then the tool result
    second = client.calls[1]["messages"]
    assert second[1]["content"][0].type == "thinking"
    assert second[2]["content"][0]["tool_use_id"] == "t1"


def test_tool_errors_are_reported_back(h):
    client = h.FakeClient(
        h.reply(h.tool_use("t1", "lookup_order", order_id="TS-9999")),
        h.reply(h.text("I couldn't find order TS-9999.")),
    )
    run = run_agent("refund TS-9999", client=client, model="m")
    assert run.steps[0]["error"].startswith("Error: no order")
    result = client.calls[1]["messages"][2]["content"][0]
    assert result["is_error"] is True


def test_refusal_and_runaway_loops_are_errors(h):
    run = run_agent("x", client=h.FakeClient(h.reply(h.text(""), stop_reason="refusal")), model="m")
    assert run.error == "model refused the request"
    loop = [h.reply(h.tool_use(f"t{i}", "lookup_order", order_id="TS-1001")) for i in range(MAX_TURNS)]
    run = run_agent("x", client=h.FakeClient(*loop), model="m")
    assert run.error and "turns" in run.error


def test_unknown_tool_and_bad_args():
    box = ToolBox()
    assert box.call("teleport", {}) == ("Error: unknown tool 'teleport'", True)
    assert box.call("refund", {"order_id": "TS-1001"})[1] is True


def test_system_prompt_has_todays_date():
    assert "Today's date is 2026-10-01." in system_prompt()
    assert "{today}" not in system_prompt()


def test_tool_definitions_are_strict():
    for t in load_tool_definitions():
        assert t["strict"] is True and t["input_schema"]["additionalProperties"] is False


# --- the Verdict side -------------------------------------------------------------

verdict = pytest.importorskip("verdict")


def test_adapter_reports_steps_cost_and_passes_trajectory_checks(h, monkeypatch):
    from verdict.ci.suite import load_suite
    from verdict.config import settings

    # Verdict's settings require a key even with an injected client; nothing is called.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-used")
    settings.get_settings.cache_clear()
    from verdict.evals.trajectory import check_trajectory
    from verdict.models.schemas import TestPrompt
    from verdict.models.trace_schemas import TrajectoryExpectation

    from verdict_adapter import SupportAgent

    client = h.FakeClient(
        h.reply(h.tool_use("t1", "lookup_order", order_id="TS-1001")),
        h.reply(h.tool_use("t2", "refund", order_id="TS-1001", amount=89.0, reason="leaks")),
        h.reply(h.text("Refunded $89.00.")),
    )
    adapter = SupportAgent(client=client)
    case = next(c for c in load_suite(ROOT / "evals/core.jsonl") if c.id == "refund-in-window")
    [res] = asyncio.run(adapter.execute_batch([TestPrompt(**case.model_dump())]))
    assert res.error is None and res.model_used == "claude-opus-5-5"
    assert [s.step_type for s in res.steps] == ["tool_call", "tool_call", "final_answer"]
    assert res.estimated_cost_usd == pytest.approx((3000 * 4 + 300 * 20) / 1e6)
    traj = check_trajectory(res.steps, res.response,
                            TrajectoryExpectation(**case.metadata["expected_trajectory"]))
    assert traj.passed, traj.findings


def test_suite_matches_the_data():
    from verdict.ci.suite import load_suite

    cases = load_suite(ROOT / "evals/core.jsonl")
    orders = load_data()["orders"]
    assert len(cases) == 19
    for c in cases:
        for a in c.metadata.get("expected_trajectory", {}).get("args", []):
            oid = a["args"]["order_id"]
            assert a["args"]["amount"] == orders[oid]["total"], c.id  # full refunds only


def test_boundary_cases_sit_on_the_boundary():
    data = load_data()
    today = date.fromisoformat(data["today"])
    delivered = {k: v["delivered_on"] for k, v in data["orders"].items()}
    assert date.fromisoformat(delivered["TS-1008"]) == today - timedelta(days=30)
    assert date.fromisoformat(delivered["TS-1009"]) == today - timedelta(days=31)
    assert data["orders"]["TS-1007"]["total"] == 200.00


def test_calibration_labels_load_and_are_balanced():
    from verdict.ci.calibrate import load_labels

    labels = load_labels(ROOT / "evals/human_labels.jsonl")
    assert len(labels) == 20
    assert sum(not e.human_passed for e in labels) == 10


def test_verdict_yaml_is_valid():
    from verdict.ci.config import load_config

    cfg = load_config(ROOT / "verdict.yaml")
    assert cfg.suite_path == (ROOT / "evals/core.jsonl").resolve()
    assert json.loads((ROOT / "tools/refund.json").read_text())["name"] == "refund"
