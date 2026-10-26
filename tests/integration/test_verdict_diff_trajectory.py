"""End to end: a tool-policy change the text judge can't see, caught by trajectory checks.

The sample agent reads tools/policy.json to decide which tools to call. Head drops the
order lookup. Its answers read identically, so the (fake) judge passes everything; the
case's expected_trajectory is what fails the gate.
"""

import json
import textwrap

import pytest
from click.testing import CliRunner

import verdict.ci.diff as ci_diff
from tests.integration.test_verdict_diff_git import _commit, _git
from verdict.cli import main
from verdict.models.schemas import Judgment

AGENT = textwrap.dedent(
    """
    import json
    from pathlib import Path

    from verdict.adapters.base import TargetAdapter
    from verdict.models.trace_schemas import TraceStep


    class Agent(TargetAdapter):
        name = "tool-agent"
        version = "1"

        async def execute(self, prompt, prompt_id):
            tools = json.loads(Path("tools/policy.json").read_text())["call"]
            steps = [TraceStep(step_id=i, step_type="tool_call", tool_name=t,
                               tool_arguments={"order_id": "A1"}, tool_result="ok")
                     for i, t in enumerate(tools)]
            answer = "Refunded order A1."
            steps.append(TraceStep(step_id=len(steps), step_type="final_answer", llm_output=answer))
            return self.make_result(prompt_id, answer, steps=steps)
    """
)

CASE = {
    "id": "refund-a1",
    "prompt": "Please refund order A1.",
    "expected_behavior": "Refunds order A1.",
    "expected_trajectory": {
        "tools": ["lookup_order", "refund"],
        "args": [{"tool": "refund", "args": {"order_id": "A1"}}],
    },
}


def always_pass(prompts, results):
    return [Judgment(prompt_id=p.id, passed=True, judge_model="fake",
                     reasoning="The response confirms the refund.") for p in prompts]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "agent-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, {
        "agent.py": AGENT,
        "verdict.yaml": "target: agent.py:Agent\nwatch: ['tools/*.json']\n"
                        "suite: evals/core.jsonl\nruns: 4\n",
        "evals/core.jsonl": json.dumps(CASE) + "\n",
        "tools/policy.json": json.dumps({"call": ["lookup_order", "refund"]}),
    }, "base")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(ci_diff, "llm_judge", lambda model: always_pass)
    return repo


def test_skipped_lookup_is_caught_although_the_judge_passes(repo):
    _commit(repo, {"tools/policy.json": json.dumps({"call": ["refund"]})}, "skip lookup")
    r = CliRunner().invoke(main, ["diff", "--base", "main~1"], catch_exceptions=False)
    assert r.exit_code == 2, r.output

    data = json.loads((repo / "verdict-diff.json").read_text())
    assert data["suite"]["base"]["pass_rate"] == 1.0
    assert data["suite"]["head"]["pass_rate"] == 0.0
    assert data["suite"]["head"]["trajectory_failures"] == 4
    assert data["suite"]["base"]["mean_tool_calls"] == 2.0
    assert data["suite"]["head"]["mean_tool_calls"] == 1.0
    [case] = data["cases"]
    assert case["status"] == "regressed"
    assert case["head_failures"] == [
        "trajectory: expected lookup_order → refund (in order), got refund"
    ]
    md = (repo / "verdict-diff.md").read_text()
    assert "| Trajectory failures | 0 | 4 | |" in md


def test_same_trajectory_passes(repo):
    _commit(repo, {"tools/policy.json": json.dumps({"call": ["lookup_order", "refund"],
                                                     "note": "reordered keys"})}, "noop")
    r = CliRunner().invoke(main, ["diff", "--base", "main~1"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
