import pytest

from verdict.ci.config import ConfigError, load_config, match_watch
from verdict.ci.suite import SuiteError, load_suite


def test_load_config_handoff_example(tmp_path):
    cfg_file = tmp_path / "verdict.yaml"
    cfg_file.write_text(
        """
target: agent.py:Agent
watch: ["prompts/**", "skills/**", "tools/*.json"]
suite: evals/core.jsonl
runs: 10
judge: { model: claude-sonnet-5-5, calibration: evals/human_labels.jsonl, min_kappa: 0.7 }
gate:
  max_pass_rate_drop: 0.05
  significance: 0.05
  cost_increase_max: 0.20
"""
    )
    cfg = load_config(cfg_file)
    assert cfg.runs == 10
    assert cfg.judge.model == "claude-sonnet-5-5"
    assert cfg.gate.cost_increase_max == 0.20
    assert cfg.stats.method == "fisher"
    assert cfg.suite_path == (tmp_path / "evals/core.jsonl").resolve()


def test_config_rejects_unknown_keys(tmp_path):
    f = tmp_path / "verdict.yaml"
    f.write_text("target: a.py:A\nsuite: s.jsonl\ngates: {}\n")
    with pytest.raises(ConfigError, match="gates"):
        load_config(f)


def test_config_missing(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    "path,matched",
    [
        ("prompts/system.txt", True),
        ("prompts/a/b/c.md", True),
        ("skills/x/SKILL.md", True),
        ("tools/search.json", True),
        ("tools/nested/search.json", False),
        ("src/app.py", False),
        ("README.md", False),
    ],
)
def test_match_watch(path, matched):
    patterns = ["prompts/**", "skills/**", "tools/*.json"]
    assert (match_watch([path], patterns) == [path]) is matched


def test_match_watch_double_star_prefix_and_dot_paths():
    assert match_watch(["a/b/x.yaml", "x.yaml"], ["**/*.yaml"]) == ["a/b/x.yaml", "x.yaml"]
    assert match_watch([".github/p.md"], ["./.github/*.md"]) == [".github/p.md"]


def test_empty_watch_matches_everything():
    assert match_watch(["a", "b/c"], []) == ["a", "b/c"]


def test_load_suite_defaults_and_metadata(tmp_path):
    f = tmp_path / "core.jsonl"
    f.write_text(
        '# comment\n'
        '{"id": "a", "prompt": "hi", "expected_behavior": "greets", "tags": ["x"]}\n'
        "\n"
        '{"prompt": "2+2?", "expected_behavior": "says 4", "category": "edge_case"}\n'
    )
    cases = load_suite(f)
    assert [c.id for c in cases] == ["a", "case-004"]
    assert cases[0].category == "correctness"
    assert cases[0].metadata == {"tags": ["x"]}
    assert cases[1].category == "edge_case"


@pytest.mark.parametrize(
    "content,msg",
    [
        ("not json\n", "invalid JSON"),
        ('{"prompt": "x"}\n', "required"),
        ('{"id": "a", "prompt": "x", "expected_behavior": "y"}\n' * 2, "duplicate"),
        ("", "no cases"),
    ],
)
def test_load_suite_errors(tmp_path, content, msg):
    f = tmp_path / "s.jsonl"
    f.write_text(content)
    with pytest.raises(SuiteError, match=msg):
        load_suite(f)
