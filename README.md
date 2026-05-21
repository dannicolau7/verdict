# Verdict

> Evaluation infrastructure for AI agents.

[![CI](https://github.com/dannicolau7/verdict/actions/workflows/test.yml/badge.svg)](https://github.com/dannicolau7/verdict/actions/workflows/test.yml)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/pypi/v/verdict-eval)

## Demo

<!-- Replace the link below after recording with `asciinema rec docs/demo.cast --command ./scripts/demo.sh` -->
> Recording coming soon — run `./scripts/demo.sh` locally after `pip install verdict-eval`.

## Install

```bash
pip install verdict-eval
```

## Quickstart

```bash
# Run an evaluation against a built-in adapter
verdict eval --target simple_rag --num-per-category 5

# Compare two adapter versions
verdict diff --target-a simple_rag --target-b path/to/v2.py:MyAdapter --num 10

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

Compare two adapter versions against the same generated test suite.

```bash
verdict diff \
  --target-a simple_rag \
  --target-b path/to/v2.py:V2Adapter \
  --num 10
```

### `verdict flakiness`

Analyze judge and target consistency across historical evaluation runs.

```bash
verdict flakiness --target my-system --min-runs 5 --reports-dir ./reports
```

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
| Pass/fail agreement (non-borderline) | ≥ 80% | TBD |
| Critical failure detection | 5 / 5 | TBD |
| Score accuracy (±1) | ≥ 70% | TBD |

Run calibration locally (requires `ANTHROPIC_API_KEY`):

```bash
pytest tests/qa/test_judge_calibration.py -v -m llm
```

See [docs/judge_calibration.md](docs/judge_calibration.md) for full methodology.

## License

MIT — see [LICENSE](LICENSE).
