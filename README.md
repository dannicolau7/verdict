# Verdict

> Evaluation infrastructure for AI agents.

[![CI](https://github.com/dannicolau7/verdict/actions/workflows/test.yml/badge.svg)](https://github.com/dannicolau7/verdict/actions/workflows/test.yml)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/pypi/v/verdict-eval)

## Demo

[![asciicast](https://asciinema.org/a/1114001.svg)](https://asciinema.org/a/1114001)

## Install

```bash
pip install verdict-eval
```

## Quickstart

```bash
# Run an evaluation against a built-in adapter
verdict eval --target simple_rag --num-per-category 5

# Did this prompt/skill/tool change make my agent worse?
verdict diff --base origin/main --head HEAD --config verdict.yaml

# How well does the judge agree with human labels?
verdict calibrate --labels evals/human_labels.jsonl --min-kappa 0.7

# Analyze flakiness across historical runs
verdict flakiness --target my-system --reports-dir ./reports
```

## CLI reference

### `verdict eval`

Run a full evaluation against a target adapter.

| Flag | Default | Description |
|------|---------|-------------|
| `--target` | required | Adapter spec: `simple_rag` or `path/to/file.py:ClassName` |
| `--num-per-category` | 5 | Prompts per test category |
| `--categories` | all | Specific categories (repeat for multiple) |
| `--output-dir` | `./reports` | Report output directory |
| `--run-id` | auto | Custom run identifier |
| `--model` | settings default | Override LLM model for all agents |
| `--bootstrap-iterations` | 1000 | Bootstrap CI iterations (0 to disable) |
| `--max-cost-usd` | — | Fail (exit 2) if total cost exceeds this amount |
| `--max-total-latency-seconds` | — | Fail (exit 2) if total latency exceeds this |
| `--fail-on-pass-rate-below` | — | Fail (exit 2) if pass rate < threshold |
| `--fail-on-ci-low-below` | — | Fail (exit 2) if CI lower bound < threshold |
| `--cache-mode` | `off` | `off` / `record` / `replay` / `update` |
| `--cache-dir` | `.verdict_cache` | Directory for cached responses |
| `--adaptive` | off | Run adaptive follow-up probes based on initial responses |

### `verdict diff`

**Did this change make my agent worse?** Code changes get CI; prompt, skill,
tool-definition and model changes usually don't. `verdict diff` runs your eval suite
N times on two git refs and tells you whether the difference is real or noise.

```bash
verdict diff --base origin/main --head HEAD --config verdict.yaml
```

```yaml
# verdict.yaml
target: agent/verdict_adapter.py:SupportAgent   # a TargetAdapter in your repo
watch: ["prompts/**", "skills/**", "tools/*.json"]
suite: evals/core.jsonl
runs: 10
judge: { model: claude-sonnet-5-5 }
gate:
  max_pass_rate_drop: 0.05   # fail if pass rate drops > 5 pts …
  significance: 0.05         # … and the drop is significant (p < 0.05)
  cost_increase_max: 0.20    # fail if mean cost per run rises > 20%
# optional: gate.latency_increase_max, gate.fail_on_case_regression,
#           stats: { method: fisher | bootstrap, bootstrap_iterations, seed }
```

`evals/core.jsonl` holds one case per line:
`{"id": "refund-window", "prompt": "…", "expected_behavior": "…"}`
(`category` and `severity` are optional).

How it works:

1. Lists files changed on `--head` since it left `--base`. If none match `watch`,
   it writes a "skipped" result and exits 0 (`--force` to run anyway).
2. Checks each ref out into a temporary git worktree and runs the target there, in its
   own process, so prompts and code come from that ref. The suite is read once from
   the current checkout so both sides run the same cases.
3. Judges every response with the same judge, then reports per-suite and per-case
   pass rate with a Wilson 95% CI, a significance test (Fisher's exact by default,
   bootstrap optional), and cost and latency deltas.
4. Writes `verdict-diff.md` (a PR comment: verdict, regressions, failing cases,
   summary) and `verdict-diff.json`, and exits **2** if the gate is breached.

| Flag | Default | Description |
|------|---------|-------------|
| `--base` | — | Git ref to compare against |
| `--head` | `HEAD` | Git ref under test |
| `--config` | `verdict.yaml` | Config file; paths in it are relative to it |
| `--runs` | from config | Runs per side |
| `--stats` | from config | `fisher` or `bootstrap` |
| `--force` | off | Run even if no watched files changed |
| `--json-out` / `--md-out` | `verdict-diff.json` / `.md` | Output paths |

In GitHub Actions, check out with `fetch-depth: 0` so the base ref is available.

The older adapter-vs-adapter mode still works:
`verdict diff --target-a simple_rag --target-b path/to/v2.py:V2Adapter --num 10`.

### `verdict calibrate`

**Can you trust the judge?** `verdict diff` is only as good as its judge. `verdict
calibrate` judges human-labeled examples and reports Cohen's κ (95% bootstrap CI),
agreement, the confusion matrix, failure-detection precision/recall per rubric and per
failure mode, and every disagreement. It exits **2** when κ < `min_kappa`.

```bash
verdict calibrate                     # reads judge.calibration / model / min_kappa from verdict.yaml
verdict calibrate --labels evals/human_labels.jsonl --judge-model claude-sonnet-5-5 --min-kappa 0.7
```

Labels are JSONL, one per line:
`{"id": "…", "prompt": "…", "response": "…", "expected_behavior": "…", "label": "pass"|"fail"}`
(optional: `category`, `severity`, `failure_mode`, `borderline`). The nested format of
`tests/qa/judge_calibration.json` works too. Outputs: `verdict-calibrate.md` and
`verdict-calibrate.json`. See [docs/judge_calibration.md](docs/judge_calibration.md).

### `verdict flakiness`

Analyze judge and target consistency across historical evaluation runs.

```bash
verdict flakiness --target my-system --min-runs 5 --reports-dir ./reports
```

### `verdict compliance`

Map an eval report to **HIPAA Security Rule** and **NIST AI RMF** controls, producing
machine-readable and human-readable compliance artifacts.

```bash
# After running verdict eval, point at the JSON report:
verdict compliance --report ./reports/eval_abc123.json --output-dir ./compliance
```

Outputs two files:

| File | Description |
|------|-------------|
| `compliance_{run_id}.json` | Machine-readable audit artifact — control IDs, evidence entries, bootstrap CIs, token/cost provenance, eval hash |
| `compliance_{run_id}.md` | Human-readable control-by-control report |

**Frameworks covered:** 5 HIPAA Security Rule controls (general, administrative, and
technical safeguards) and 8 NIST AI RMF controls (MAP, MEASURE, MANAGE functions) — a
curated subset that maps naturally to eval outcomes.

**What makes this statistically grounded:**
- Each control's evidence entry includes a per-source 95% bootstrap CI
- Controls aggregated from multiple categories carry a combined CI
- Flakiness-detected prompts reduce the confidence rating for affected controls
- Token/cost provenance is recorded in `provenance` for full audit traceability

**Python API:**
```python
from verdict.compliance import generate_audit_artifact, save_artifacts
from verdict.models.schemas import EvalReport
import json

report = EvalReport(**json.loads(Path("eval_report.json").read_text()))
artifact = generate_audit_artifact(report)
json_path, md_path = save_artifacts(artifact, Path("./compliance"), report.run_id)
```

See `examples/compliance_example.py` for a runnable demo with synthetic data.

## Web UI

Verdict ships a local web interface — a FastAPI backend with a React/TypeScript
frontend — as an alternative to the CLI.

### Start

```bash
# 1. Backend (from repo root)
cd web && uvicorn backend.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd web/frontend && npm install && npm run dev
```

Open **http://localhost:5173**. The API docs are at **http://localhost:8000/docs**.

Requires `ANTHROPIC_API_KEY` in the environment before starting the backend.

### Features

| Page | Status | Description |
|------|--------|-------------|
| Run evaluation | ✅ | Configure and launch an eval; streams live progress via SSE |
| Diff | 🚧 | Compare two adapter versions — coming soon |
| History | 🚧 | Browse past runs — coming soon |

The **Run evaluation** page exposes all core options: test categories, prompts
per category, attack mode (standard / adaptive), bootstrap CI, flakiness
detection, and judge model. The **Advanced → Custom prompts** textarea lets
you pin specific inputs that always run alongside the generated suite — useful
for regression tests or known-tricky inputs.

### Custom prompts

Paste one prompt per line in the "Custom prompts" textarea (Advanced options).
Choose a category to assign to all of them. They are prepended to the generated
test suite and judged identically to auto-generated prompts.

## Adaptive mode

When `--adaptive` is enabled, Verdict runs a second pass of follow-up probes selected
based on each initial response. Pattern selection is **entirely rule-based** — no LLM
is used to generate new attacks. All probes are composed from the curated
[OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
pattern library in `verdict/evals/attack_patterns/patterns.json`.

This design ensures Verdict remains a defensive evaluation tool. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the security boundary policy.

```bash
verdict eval --target simple_rag --adaptive
```

## Writing a custom adapter

```python
# my_adapter.py
from verdict.adapters.base import TargetAdapter
from verdict.models.schemas import ExecutionResult, TestPrompt

class MyAdapter(TargetAdapter):
    name = "my-system"
    version = "1.0.0"

    async def execute(self, prompt: TestPrompt) -> ExecutionResult:
        response = call_my_system(prompt.prompt)
        return self.make_result(prompt, response=response)
```

```bash
verdict eval --target my_adapter.py:MyAdapter
```

## Test categories

| Category | What it evaluates |
|----------|-------------------|
| `correctness` | Factual accuracy and reasoning quality |
| `safety` | Refusal of harmful, dangerous, or unethical requests |
| `injection` | Robustness against prompt injection (OWASP LLM01, LLM07) |
| `edge_case` | Graceful handling of malformed and ambiguous inputs |
| `compliance` | Privacy and data handling (OWASP LLM02) |

## Judge calibration

The Judge is validated against 22 hand-labeled examples covering all five test
categories. Results are produced by running the live judge against known ground
truth — no labels were derived from judge output.

| Metric | Target | Baseline |
|--------|--------|----------|
| Pass/fail agreement (non-borderline) | ≥ 80% | **100%** (18/18) |
| Critical failure detection | 5 / 5 | **5 / 5** |
| Score accuracy (±1) | ≥ 70% | **100%** (10/10) |

*Measured on claude-sonnet-4-6, 2026-05-22.*

Run calibration locally (requires `ANTHROPIC_API_KEY`):

```bash
verdict calibrate --labels tests/qa/judge_calibration.json --min-kappa 0.7
# or the pytest version with the thresholds above:
pytest tests/qa/test_judge_calibration.py -v -m llm
```

See [docs/judge_calibration.md](docs/judge_calibration.md) for full methodology.

## License

MIT — see [LICENSE](LICENSE).
