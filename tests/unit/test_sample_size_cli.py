import json

from click.testing import CliRunner

from verdict.cli import main


def test_flags_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["sample-size", "--baseline", "0.9", "--drop", "0.05",
                                  "--cases", "20"])
    assert r.exit_code == 0, r.output
    assert "686" in r.output and "runs: 35 with 20 cases" in r.output


def test_reads_config_and_reports_shortfall(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "core.jsonl").write_text(
        "\n".join(json.dumps({"id": f"c{i}", "prompt": "p", "expected_behavior": "e"})
                  for i in range(20)) + "\n"
    )
    (tmp_path / "verdict.yaml").write_text(
        "target: a.py:A\nsuite: core.jsonl\nruns: 10\ngate: {max_pass_rate_drop: 0.05}\n"
    )
    r = CliRunner().invoke(main, ["sample-size", "--baseline", "0.9"])
    assert r.exit_code == 0, r.output
    assert "with 20 cases" in r.output
    assert "runs: 10 → 200 per side" in r.output and "not enough" in r.output


def test_invalid_drop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["sample-size", "--baseline", "0.3", "--drop", "0.5"])
    assert r.exit_code == 2 and "drop" in r.output
