"""End-to-end `verdict diff --base/--head` on a throwaway git repo.

Real git worktrees and the real side-runner subprocess; only the judge is faked.
The sample agent echoes its system prompt from prompts/system.txt, so editing that
file is the "prompt change" under test.
"""

import json
import subprocess
import textwrap

import pytest
from click.testing import CliRunner

import verdict.ci.diff as ci_diff
from verdict.cli import main
from verdict.models.schemas import Judgment

AGENT = textwrap.dedent(
    """
    from pathlib import Path

    from verdict.adapters.base import TargetAdapter


    class Agent(TargetAdapter):
        name = "sample-agent"
        version = "1"

        async def execute(self, prompt, prompt_id):
            system = Path("prompts/system.txt").read_text()
            r = self.make_result(prompt_id, f"{system} {prompt}")
            r.estimated_cost_usd = 0.001 * len(system.split())
            return r
    """
)

CONFIG = textwrap.dedent(
    """
    target: agent.py:Agent
    watch: ["prompts/**"]
    suite: evals/core.jsonl
    runs: 5
    gate:
      max_pass_rate_drop: 0.05
      significance: 0.05
    """
)

CASES = [
    {"id": "refund", "prompt": "Refund after 40 days?", "expected_behavior": "mentions 30 days"},
    {"id": "late", "prompt": "Late refund?", "expected_behavior": "mentions 30 days"},
    {"id": "hello", "prompt": "Hi", "expected_behavior": "greets"},
]


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True,
    )


def _commit(repo, files, msg):
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def fake_judge(prompts, results):
    by_id = {r.prompt_id: r for r in results}
    out = []
    for p in prompts:
        ok = "greets" in p.expected_behavior or "30 days" in by_id[p.id].response
        out.append(Judgment(prompt_id=p.id, passed=ok, judge_model="fake",
                            reasoning="Checked the response for the refund window."
                            if ok else "Response never states the 30 day refund window."))
    return out


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "agent-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, {
        "agent.py": AGENT,
        "verdict.yaml": CONFIG,
        "evals/core.jsonl": "\n".join(json.dumps(c) for c in CASES) + "\n",
        "prompts/system.txt": "Refunds are accepted within 30 days.",
    }, "base")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(ci_diff, "llm_judge", lambda model: fake_judge)
    return repo


def _run(*args):
    return CliRunner().invoke(main, ["diff", *args], catch_exceptions=False)


def test_prompt_regression_fails_gate(repo):
    _commit(repo, {"prompts/system.txt": "Be brief and friendly."}, "shorter prompt")
    result = _run("--base", "main~1", "--head", "main")
    assert result.exit_code == 2, result.output

    data = json.loads((repo / "verdict-diff.json").read_text())
    assert data["status"] == "completed"
    assert data["watched_changes"] == ["prompts/system.txt"]
    assert data["suite"]["base"]["pass_rate"] == 1.0
    assert data["suite"]["head"]["pass_rate"] == pytest.approx(1 / 3)
    assert data["gate"]["breaches"] == ["pass_rate"]
    assert {c["case_id"] for c in data["cases"] if c["status"] == "regressed"} == {"refund", "late"}
    assert data["suite"]["cost_delta_pct"] < 0  # shorter system prompt is cheaper

    md = (repo / "verdict-diff.md").read_text()
    assert "regression detected" in md
    assert "30 day refund window" in md


def test_harmless_prompt_change_passes(repo):
    _commit(repo, {"prompts/system.txt": "Refunds are accepted within 30 days. Be kind."}, "tone")
    result = _run("--base", "main~1", "--runs", "3")
    assert result.exit_code == 0, result.output
    data = json.loads((repo / "verdict-diff.json").read_text())
    assert data["runs"] == 3
    assert data["suite"]["delta"] == 0
    assert "✅ Verdict: no regression" in (repo / "verdict-diff.md").read_text()


def test_unwatched_change_is_skipped(repo):
    _commit(repo, {"README.md": "docs"}, "docs only")
    result = _run("--base", "main~1", "--json-out", "out/r.json", "--md-out", "out/r.md")
    assert result.exit_code == 0, result.output
    assert json.loads((repo / "out/r.json").read_text())["status"] == "skipped"
    assert "skipped" in (repo / "out/r.md").read_text()


def test_force_runs_without_watched_changes(repo):
    _commit(repo, {"README.md": "docs"}, "docs only")
    result = _run("--base", "main~1", "--force", "--runs", "1")
    assert result.exit_code == 0, result.output
    assert json.loads((repo / "verdict-diff.json").read_text())["status"] == "completed"


def test_bad_ref_is_a_clean_error(repo):
    result = CliRunner().invoke(main, ["diff", "--base", "nope"])
    assert result.exit_code == 1
    assert "cannot resolve ref 'nope'" in result.output


def test_requires_a_mode():
    result = CliRunner().invoke(main, ["diff"])
    assert result.exit_code == 2
    assert "--base" in result.output
