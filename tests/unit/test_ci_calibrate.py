import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import verdict.ci.calibrate as cal
from verdict.ci.calibrate import LabelError, analyze_calibration, load_labels
from verdict.ci.comment import CALIBRATE_MARKER, render_calibration_markdown
from verdict.cli import main
from verdict.models.schemas import FailureMode, Judgment

SHIPPED = Path(__file__).parents[1] / "qa" / "judge_calibration.json"


def _row(i, label, mode=None, category="correctness", **kw):
    row = {"id": f"ex-{i}", "prompt": f"q{i}", "response": f"r{i}",
           "expected_behavior": "answers correctly", "category": category, "label": label}
    if mode:
        row["failure_mode"] = mode
    row.update(kw)
    return row


def _write(tmp_path, rows, name="labels.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _judge_from(verdicts):
    """Fake judge: verdicts maps prompt id -> (passed, failure_mode) or 'error'."""
    def judge(prompts, results):
        out = []
        for p in prompts:
            v = verdicts.get(p.id, (True, None))
            if v == "error":
                out.append(Judgment(prompt_id=p.id, passed=False, judge_model="fake",
                                    reasoning="Judge failed to produce valid output.",
                                    failure_mode=FailureMode.other, metadata={"judge_error": True}))
            else:
                out.append(Judgment(prompt_id=p.id, passed=v[0], judge_model="fake",
                                    failure_mode=FailureMode(v[1]) if v[1] else None,
                                    reasoning=f"Fake judge verdict for {p.id} here."))
        return out
    return judge


def test_load_shipped_nested_dataset():
    examples = load_labels(SHIPPED)
    assert len(examples) == 22
    assert sum(e.borderline for e in examples) == 4
    assert sum(not e.human_passed for e in examples) == 12
    assert all(e.result.prompt_id == e.prompt.id for e in examples)


def test_load_flat_jsonl_and_passed_bool(tmp_path):
    p = _write(tmp_path, [_row(1, "pass"), {**_row(2, "x"), "label": None, "passed": False}])
    ex = load_labels(p)
    assert [e.human_passed for e in ex] == [True, False]
    assert ex[0].prompt.category == "correctness"


@pytest.mark.parametrize("row,msg", [
    ({"prompt": "q", "response": "r", "expected_behavior": "e", "label": "pass"}, "'id'"),
    ({"id": "a", "prompt": "q", "expected_behavior": "e", "label": "pass"}, "'response'"),
    ({"id": "a", "prompt": "q", "response": "r", "expected_behavior": "e", "label": "maybe"}, "label"),
    ({"id": "a", "prompt": "q", "response": "r", "expected_behavior": "e", "label": "pass",
      "category": "vibes"}, "category"),
])
def test_load_errors(tmp_path, row, msg):
    with pytest.raises(LabelError, match=msg):
        load_labels(_write(tmp_path, [row]))


def test_duplicate_ids(tmp_path):
    with pytest.raises(LabelError, match="duplicate"):
        load_labels(_write(tmp_path, [_row(1, "pass"), _row(1, "fail")]))


def test_perfect_judge():
    examples = load_labels(SHIPPED)
    verdicts = {e.prompt.id: (e.human_passed, e.human_failure_mode) for e in examples}
    r = analyze_calibration(examples, _judge_from(verdicts)(
        [e.prompt for e in examples], [e.result for e in examples]), min_kappa=0.7)
    assert r.kappa == 1.0 and r.agreement == 1.0 and r.passed
    assert r.n_scored == 18 and r.n_borderline == 4
    assert r.disagreements == []
    assert all(m.precision == 1.0 and m.recall == 1.0 for m in r.by_failure_mode)


def test_disagreements_errors_and_breakdowns(tmp_path):
    rows = [
        _row(1, "fail", "hallucination"), _row(2, "fail", "hallucination"),
        _row(3, "pass"), _row(4, "pass"),
        _row(5, "fail", "pii_leak", category="compliance"), _row(6, "pass", category="compliance"),
        _row(7, "fail", borderline=True), _row(8, "pass"),
    ]
    examples = load_labels(_write(tmp_path, rows))
    judge = _judge_from({
        "ex-1": (False, "hallucination"),
        "ex-2": (True, None),             # missed failure
        "ex-3": (False, "format_error"),  # false alarm
        "ex-5": (False, "compliance_violation"),  # right verdict, wrong mode
        "ex-8": "error",
    })
    r = analyze_calibration(examples, judge([e.prompt for e in examples],
                                            [e.result for e in examples]), min_kappa=0.7)
    assert (r.n_total, r.n_scored, r.n_borderline, r.n_judge_errors) == (8, 6, 1, 1)
    assert r.confusion == {"pass_pass": 2, "pass_fail": 1, "fail_pass": 1, "fail_fail": 2}
    assert r.kappa == pytest.approx(1 / 3)
    assert not r.passed
    assert {i.id for i in r.disagreements} == {"ex-2", "ex-3"}
    assert (r.fail_precision, r.fail_recall) == (pytest.approx(2 / 3), pytest.approx(2 / 3))
    cats = {g.name: g for g in r.by_category}
    assert cats["compliance"].agreement == 1.0 and cats["correctness"].n == 4
    modes = {m.mode: m for m in r.by_failure_mode}
    assert modes["hallucination"].recall == 0.5 and modes["hallucination"].precision == 1.0
    assert modes["pii_leak"].recall == 0.0 and modes["pii_leak"].precision is None
    assert modes["format_error"].support == 0

    md = render_calibration_markdown(r)
    assert md.startswith(CALIBRATE_MARKER)
    assert "κ below 0.7" in md
    assert md.index("#### Disagreements") < md.index("#### Confusion matrix")
    assert "1 judge errors excluded" in md and "Only 6 scored examples" in md


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-tests")
    holder = {"verdicts": {}}
    monkeypatch.setattr(cal, "llm_judge", lambda model: _judge_from(holder["verdicts"]))
    return holder


def test_cli_reads_config_and_gates(tmp_path, cli_env):
    rows = [_row(i, "pass") for i in range(5)] + [_row(i, "fail", "hallucination")
                                                 for i in range(5, 10)]
    (tmp_path / "evals").mkdir()
    _write(tmp_path, rows, "evals/human_labels.jsonl")
    (tmp_path / "verdict.yaml").write_text(
        "target: a.py:A\nsuite: s.jsonl\n"
        "judge: {model: some-judge, calibration: evals/human_labels.jsonl, min_kappa: 0.7}\n"
    )
    cli_env["verdicts"] = {f"ex-{i}": (False, "hallucination") for i in range(5, 10)}
    ok = CliRunner().invoke(main, ["calibrate"], catch_exceptions=False)
    assert ok.exit_code == 0, ok.output
    data = json.loads((tmp_path / "verdict-calibrate.json").read_text())
    assert data["kappa"] == 1.0 and data["judge_model"] == "some-judge"

    cli_env["verdicts"] = {f"ex-{i}": (False, "hallucination") for i in range(3, 8)}
    bad = CliRunner().invoke(main, ["calibrate", "--md-out", "out/c.md"], catch_exceptions=False)
    assert bad.exit_code == 2, bad.output
    assert "κ below 0.7" in (tmp_path / "out/c.md").read_text()
    assert set(json.loads((tmp_path / "verdict-calibrate.json").read_text())["disagreements"]) \
        == {"ex-3", "ex-4", "ex-8", "ex-9"}


def test_cli_flags_without_config(tmp_path, cli_env):
    p = _write(tmp_path, [_row(1, "pass"), _row(2, "fail")])
    r = CliRunner().invoke(main, ["calibrate", "--labels", str(p), "--judge-model", "j"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output  # no min_kappa -> report only


def test_cli_errors(tmp_path, cli_env):
    r = CliRunner().invoke(main, ["calibrate"])
    assert r.exit_code == 2 and "No labels" in r.output
    r = CliRunner().invoke(main, ["calibrate", "--labels", "missing.jsonl", "--judge-model", "j"])
    assert r.exit_code == 1 and "not found" in r.output
