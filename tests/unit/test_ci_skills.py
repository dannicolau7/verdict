from pathlib import Path

import pytest
from click.testing import CliRunner

from verdict.ci.skills import (
    SKILLS_MARKER,
    SkillSuiteError,
    _parse_skill_choice,
    compare,
    load_baseline,
    load_skill_suites,
    load_skills,
    render_skills_markdown,
    run_skill_suites,
)
from verdict.models.schemas import Judgment

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "skills"


def _write_skill(root: Path, name: str, desc: str, body: str = "Do the thing.") -> None:
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n")


def _write_suite(root: Path, name: str, text: str) -> None:
    d = root / "tests"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text)


SUITE = """
trigger:
  - {id: t-load, prompt: "redact this", expect: redact}
  - {id: t-none, prompt: "write code", expect: null}
output:
  - {id: o-name, prompt: "Redact: Jane", expected_behavior: "Jane removed"}
"""


@pytest.fixture
def workspace(tmp_path):
    _write_skill(tmp_path, "redact", "Remove identifiers")
    _write_skill(tmp_path, "notes", "Write release notes")
    _write_suite(tmp_path, "redact", SUITE)
    return tmp_path


def keyword_router(skills, prompt):
    return "redact" if "redact" in prompt.lower() else None


def echo_responder(skill, prompt):
    return prompt.replace("Jane", "[NAME]")


def judge_by(predicate):
    def judge(prompts, results):
        return [
            Judgment(prompt_id=r.prompt_id, passed=predicate(r.response), judge_model="fake",
                     reasoning="fake judge decision for tests")
            for r in results
        ]
    return judge


GOOD_JUDGE = judge_by(lambda resp: "Jane" not in resp)


def _run(ws, router=keyword_router, responder=echo_responder, judge=GOOD_JUDGE, runs=2):
    return run_skill_suites(
        load_skills(ws / "skills"), load_skill_suites(ws / "tests"),
        router=router, responder=responder, judge=judge, runs=runs, model="m", judge_model="j",
    )


# ---------------------------------------------------------------- loading

def test_load_skills_reads_frontmatter_and_hash(workspace):
    skills = load_skills(workspace / "skills")
    assert set(skills) == {"redact", "notes"}
    assert skills["redact"].description == "Remove identifiers"
    assert skills["redact"].body == "Do the thing."
    assert len(skills["redact"].sha) == 12


def test_skill_hash_changes_when_edited(workspace):
    before = load_skills(workspace / "skills")["redact"].sha
    _write_skill(workspace, "redact", "Remove identifiers", body="Do it differently.")
    assert load_skills(workspace / "skills")["redact"].sha != before


def test_missing_dirs_and_bad_suites_raise(tmp_path):
    with pytest.raises(SkillSuiteError):
        load_skills(tmp_path / "nope")
    with pytest.raises(SkillSuiteError):
        load_skill_suites(tmp_path / "nope")
    _write_suite(tmp_path, "dup", "trigger:\n  - {id: a, prompt: x}\n  - {id: a, prompt: y}\n")
    with pytest.raises(SkillSuiteError, match="duplicate"):
        load_skill_suites(tmp_path / "tests")


def test_example_suite_loads():
    skills = load_skills(EXAMPLES / "skills")
    suites = load_skill_suites(EXAMPLES / "evals" / "skills")
    assert "pii-redaction" in skills and "release-notes" in skills
    assert suites[0].skill == "pii-redaction"


def test_parse_skill_choice():
    names = {"a", "b"}
    assert _parse_skill_choice('{"skill": "a"}', names) == "a"
    assert _parse_skill_choice('sure: {"skill": null}', names) is None
    assert _parse_skill_choice('{"skill": "zzz"}', names) is None
    assert _parse_skill_choice("no json", names) is None


# ---------------------------------------------------------------- running

def test_run_all_pass(workspace):
    report = _run(workspace)
    s = report.get("redact")
    assert s is not None
    assert (s.n, s.passed, s.pass_rate) == (6, 6, 1.0)
    assert report.fingerprint.skills["redact"] == load_skills(workspace / "skills")["redact"].sha
    assert report.fingerprint.model == "m"


def test_trigger_miss_is_recorded(workspace):
    report = _run(workspace, router=lambda skills, p: None)
    case = next(c for c in report.skills[0].cases if c.id == "t-load")
    assert case.passed == 0
    assert "got None" in case.runs[0].detail


def test_responder_error_fails_without_judge_call(workspace):
    calls = []

    def boom(skill, prompt):
        raise RuntimeError("api down")

    def judge(prompts, results):
        calls.append(len(prompts))
        return []

    report = _run(workspace, responder=boom, judge=judge)
    case = next(c for c in report.skills[0].cases if c.id == "o-name")
    assert case.passed == 0 and "api down" in case.runs[0].detail
    assert calls == []


def test_output_case_for_missing_skill_fails(tmp_path):
    _write_skill(tmp_path, "other", "x")
    _write_suite(tmp_path, "ghost", "output:\n  - {id: o, prompt: p, expected_behavior: e}\n")
    report = _run(tmp_path)
    assert report.skills[0].passed == 0
    assert report.skills[0].sha is None


# ---------------------------------------------------------------- comparing

def test_no_baseline_is_new_and_passes(workspace):
    result = compare(_run(workspace), None)
    assert result.passed
    assert [c.status for c in result.skills] == ["new"]


def test_same_results_unchanged(workspace):
    base = _run(workspace)
    result = compare(_run(workspace), base)
    assert result.passed and result.skills[0].status == "unchanged"
    assert result.fingerprint_changes == []


def test_regression_flags_newly_failing_case(workspace):
    base = _run(workspace, runs=5)
    head = _run(workspace, runs=5, judge=judge_by(lambda resp: False))
    result = compare(head, base)
    assert not result.passed
    c = result.regressions[0]
    assert c.skill == "redact" and c.newly_failing == ["o-name"]
    assert c.delta is not None and c.delta < 0


def test_single_flaky_run_is_advisory_not_a_regression(workspace):
    base = _run(workspace, runs=10)
    flaky = iter([False] + [True] * 100)
    head = _run(workspace, runs=10, judge=judge_by(lambda resp: next(flaky)))
    # 29/30 vs 30/30: drop 3.3% < max_drop, not significant; o-name fails 1 of 10 runs.
    result = compare(head, base, max_drop=0.05)
    c = result.skills[0]
    assert c.status == "unchanged" and result.passed
    assert c.newly_flaky == ["o-name"] and c.newly_failing == []
    assert "newly flaky" in render_skills_markdown(result)


def test_majority_failing_case_regresses_even_within_tolerance(workspace):
    base = _run(workspace, runs=4)
    pattern = iter([False, False, False, True] + [True] * 100)
    head = _run(workspace, runs=4, judge=judge_by(lambda resp: next(pattern)))
    # 9/12 vs 12/12, but o-name now fails 3 of 4 runs.
    result = compare(head, base, max_drop=0.5)
    assert result.skills[0].newly_failing == ["o-name"]
    assert not result.passed


def test_fingerprint_reports_skill_edit(workspace):
    base = _run(workspace)
    _write_skill(workspace, "redact", "Remove identifiers", body="New wording.")
    result = compare(_run(workspace), base)
    assert result.skills[0].skill_changed
    assert any(ch.startswith("skill redact:") for ch in result.fingerprint_changes)


def test_baseline_roundtrip(workspace, tmp_path):
    report = _run(workspace)
    p = tmp_path / "base.json"
    p.write_text(report.model_dump_json())
    loaded = load_baseline(p)
    assert loaded is not None and loaded.get("redact").passed == report.get("redact").passed
    assert load_baseline(tmp_path / "missing.json") is None


def test_markdown_verdict_first(workspace):
    base = _run(workspace, runs=5)
    head = _run(workspace, runs=5, judge=judge_by(lambda resp: False))
    md = render_skills_markdown(compare(head, base))
    lines = md.splitlines()
    assert lines[0] == SKILLS_MARKER
    assert lines[1].startswith("## ❌ Skills: 1 regressed")
    assert "`o-name`" in md
    ok = render_skills_markdown(compare(base, base))
    assert "✅" in ok.splitlines()[1]


# ---------------------------------------------------------------- CLI

def test_cli_baseline_then_regression(workspace, monkeypatch):
    import verdict.ci.diff as diff_mod
    import verdict.ci.skills as skills_mod
    from verdict.cli import main

    monkeypatch.setattr(skills_mod, "llm_router", lambda model: keyword_router)
    monkeypatch.setattr(skills_mod, "llm_responder", lambda model: echo_responder)
    monkeypatch.setattr(diff_mod, "llm_judge", lambda model: GOOD_JUDGE)
    monkeypatch.chdir(workspace)
    args = ["skills", "--skills-dir", "skills", "--tests", "tests", "--runs", "2"]

    runner = CliRunner()
    first = runner.invoke(main, args)
    assert first.exit_code == 0, first.output
    assert (workspace / "verdict-skills-baseline.json").is_file()
    assert (workspace / "verdict-skills.md").is_file()

    again = runner.invoke(main, args)
    assert again.exit_code == 0, again.output

    monkeypatch.setattr(diff_mod, "llm_judge", lambda model: judge_by(lambda r: False))
    bad = runner.invoke(main, args)
    assert bad.exit_code == 2, bad.output
