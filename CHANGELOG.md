# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] — 2026-05-22

### Fixed

- `crewai` and `langchain-anthropic` moved to optional `[crewai]` extra — these have a
  broken transitive dependency (`lancedb>=0.29.2`) that prevented `pip install verdict-eval`
  from succeeding. Core CLI functionality works without them; they are only needed for the
  upcoming D9 CrewAI Crew integration.
- Added missing `[tool.poetry.scripts]` entry point so the `verdict` CLI command is
  installed correctly.
- Renamed `verdict/cli/` package to `verdict/cli_utils/` to resolve module/package naming
  conflict that shadowed `verdict/cli.py`.

## [0.1.0] — 2026-05-20

### Added

- **Test generator** (`verdict/agents/test_generator.py`) — adversarial prompt generation across
  five categories: `correctness`, `safety`, `injection`, `edge_case`, `compliance`.
- **Executor** (`verdict/agents/executor.py`) — async batch execution against any `TargetAdapter`.
- **Judge** (`verdict/agents/judge.py`) — multi-model scoring with injection-resistant XML tagging
  and consensus averaging.
- **Reporter** (`verdict/agents/reporter.py`) — deterministic metric computation + LLM-written
  prose narrative, with post-generation % verification.
- **`SimpleRAGAdapter`** — built-in keyword RAG adapter over synthetic Acme Health Systems docs
  for local smoke testing.
- **CLI** (`verdict eval`, `verdict diff`, `verdict flakiness`) with guardrails (`--max-cost-usd`,
  `--fail-on-pass-rate-below`, `--fail-on-ci-low-below`, `--max-total-latency-seconds`).
- **Adaptive attack mode** (`--adaptive`) — rule-based follow-up probe selection from the
  23-pattern OWASP LLM Top 10 library; no LLM used for pattern generation.
- **Bootstrap CI** (`verdict/stats/bootstrap.py`) — stdlib-only 95% CI on pass rate.
- **Differential testing** (`verdict diff`) — A/B comparison of two adapter versions.
- **Flakiness detection** (`verdict flakiness`) — variance analysis across historical runs.
- **Caching** (`--cache-mode off|record|replay|update`) — filesystem and in-memory backends.
- **Token tracker** (`verdict/observability/token_tracker.py`) and pricing table
  (`verdict/costs/`) for per-run cost accounting.
- **Pydantic v2 schemas** — `TestPrompt`, `ExecutionResult`, `Judgment`, `EvalReport`,
  `DiffReport`.
- **Judge calibration dataset** — 22 hand-labeled examples in `tests/qa/judge_calibration.json`.
- GitHub Actions CI (matrix Python 3.11/3.12), OIDC-based PyPI publish workflow.

[Unreleased]: https://github.com/dannicolau7/verdict/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dannicolau7/verdict/releases/tag/v0.1.0
