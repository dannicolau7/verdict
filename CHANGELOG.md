# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-08-07

### Added

- **Web platform** (`web/`) — FastAPI backend + React 18 frontend serving four pages:
  - **Run evaluation** — SSE streaming eval pipeline (generate → execute → judge → report),
    compliance tab (HIPAA + NIST AI RMF), JSON/MD export.
  - **Diff** — fresh-run mode (shared test suite, two models, per-prompt regression tables)
    and historical mode (aggregate compare of two stored runs).
  - **Trace eval** — upload `AgentTrace` JSON, step-level judge, collapsible step timeline.
  - **History** — all past runs with label editor, filter bar, per-run export.
  - SQLite persistence via `RunStore`; runs survive backend restart.
- **`AnthropicLLMAdapter`** (`verdict/adapters/anthropic_llm.py`) — evaluate any Claude model
  as the system under test; sends each prompt as a bare user message, returns assistant text
  with token counts. Default model: `settings.default_executor_model` (Haiku).
- **Standalone eval pipeline** in web backend (`routers/eval.py`) — uses
  `generate_test_suite → execute_test_suite → judge_results → build_eval_report` directly,
  removing the CrewAI dependency from the web API path.

### Fixed

- `CacheMode.off` → `CacheMode.OFF` in `routers/eval.py` and `routers/diff.py`.
- `CategoryDiff` model missing from `api_models.py` (caused `ImportError` on startup).
- Nav "soon" badges removed from Diff and History (both pages live).
- `edge_case` displayed as `Edge_case` in Diff category table (replaced CSS `capitalize`
  with explicit label map).

## [0.3.1] — 2026-08-07

### Fixed

- **NIST AI RMF subcategory titles** — all 8 titles in `verdict/compliance/frameworks.py` now
  match verbatim text from NIST AI RMF 1.0 (January 2023); previously all were paraphrases.
- **Description framing** — NIST control descriptions changed from "directly satisfies/measures"
  to "provides evidence relevant to" throughout, reflecting the indirect nature of eval evidence.
- **Trace STEP_RUBRIC** — now differentiates by step type: `tool_call` steps judged on tool
  selection and argument validity; `tool_result`/`observation` steps on output consumption and
  error propagation; `llm_call` steps on reasoning quality; `final_answer` steps on task
  completion and answer accuracy. The previous single rubric applied tool-call criteria to all
  step types including final answers.
- **HIPAA controls absent from trace failure mode mappings** — `hallucinated_tool_call` now maps
  to `HIPAA-164.308(a)(1)(ii)(A)` (risk analysis; fabricated tool calls can invent ePHI);
  `unhandled_error` now maps to `HIPAA-164.306(a)(2)` (anticipated threats); `wrong_tool_selected`
  now maps to `NIST-MANAGE-1.3`. Previously `TRACE_FAILURE_MODE_TO_CONTROLS` contained zero HIPAA
  controls, leaving healthcare agent compliance artifacts with no HIPAA evidence.
- **XML injection escape** — `_sanitise()` in `trace_judge.py` escapes `</trace_step>` in all
  user-controlled fields, preventing payload escape from the XML wrapper.
- **`temperature=0.1`** — now correctly passed to `client.messages.create()` in trace judge;
  previously the docstring claimed it but the API call used the default (1.0).
- **Compliance wiring for `TraceEvalReport`** — `verdict compliance` command and
  `generate_audit_artifact()` now accept both `EvalReport` and `TraceEvalReport`.
- **`pytest -q` no longer fails without API key** — added `addopts = "-m 'not llm'"` to
  `[tool.pytest.ini_options]`; `@pytest.mark.llm` tests now require explicit `-m llm` opt-in.

## [0.3.0] — 2026-08-06

### Added

- **Agent-trace evaluation** (`verdict/models/trace_schemas.py`, `verdict/agents/trace_judge.py`) —
  ingests structured step-by-step agent execution logs and judges them at both the per-step and
  overall-trace level. Supports `llm_call`, `tool_call`, `tool_result`, `observation`, and
  `final_answer` step types.
- **`AgentTrace` schema** — canonical Verdict-native JSON format for recording agent runs, with
  full step metadata (tool name/arguments/result, LLM input/output, latency, error).
- **`TraceFailureMode` taxonomy** — 10 failure modes covering `wrong_tool_selected`,
  `invalid_tool_arguments`, `unhandled_error`, `premature_termination`, `unnecessary_steps`,
  `task_not_completed`, `hallucinated_tool_call`, `error_not_propagated`, `excessive_retries`,
  and `other`.
- **Trace judge** (`verdict/agents/trace_judge.py`) — injection-resistant judge using `<trace_step>`
  XML delimiters; supports single-judge and multi-judge consensus (majority vote + averaged score).
- **Trace ingestor** (`verdict/adapters/trace_ingestor.py`) — `load_trace()` / `load_traces()`
  for single files, JSON arrays, and directories of `*.json` trace files.
- **Deterministic report builder** (`verdict/reports/trace_builder.py`) — `build_trace_eval_report()`
  computes pass rate, failure mode counts, and bootstrap 95% CI; `build_trace_eval_markdown()`
  renders human-readable output.
- **New CLI command** `verdict trace-eval` with `--trace`/`--traces-dir`, `--judge-model`,
  `--output-dir`, and `--run-id` options. Outputs `trace_eval_{id}.json` + `trace_eval_{id}.md`.
- **Compliance extension** — `TRACE_FAILURE_MODE_TO_CONTROLS` mapping routes all 10 trace failure
  modes to the relevant HIPAA and NIST AI RMF controls in `verdict/compliance/mapping.py`.
- **Trace rubrics** (`verdict/evals/trace_rubrics.py`) — `OVERALL_RUBRIC` (1-5 graded) and
  `STEP_RUBRIC` (binary pass/fail) used by the trace judge prompt.
- 67 unit tests across four new test modules; no LLM calls.
- `examples/eval_agent_trace.py` — offline demo with synthetic traces (runs without API key).

## [0.2.0] — 2026-08-06

### Added

- **Compliance evidence layer** (`verdict/compliance/`) — maps eval results to 13
  curated controls across HIPAA Security Rule (5) and NIST AI RMF (8, spanning MAP,
  MEASURE, and MANAGE functions).
- Control mapping is evidence-driven: each eval category and failure mode routes to the
  controls it directly provides evidence for or against.
- Bootstrap 95% CIs computed per-control (not just run-wide), with evidence strength
  classification (high/moderate/low/insufficient) and flakiness-based confidence weighting.
- Token/cost provenance and a stable eval hash recorded in every artifact for audit
  traceability.
- Two output formats: `compliance_{run_id}.json` (machine-readable audit artifact) and
  `compliance_{run_id}.md` (human-readable control-by-control report).
- New CLI command `verdict compliance --report <path> [--output-dir <dir>]`.
- 46 unit tests for the compliance module; no LLM calls.
- `examples/compliance_example.py` — runnable demo with synthetic data.
- README section documenting the compliance layer and Python API.

## [0.1.4] — 2026-08-06

### Added

- CrewAI crew assembly (D9): all four agents (TestGenerator, Executor, Judge, Reporter)
  wired into `EvalCrew` in `verdict/crews/eval_crew.py`. CLI `eval` command now routes
  through `EvalCrew.kickoff()` with per-stage progress callbacks.
- 18 unit tests for `EvalCrew` pipeline; no LLM calls, all stages patched.

### Changed

- `scripts/demo.sh` pause timings tightened for faster demo playback.

## [0.1.3] — 2026-05-22

### Added

- Judge calibration baseline numbers (claude-sonnet-4-6): 100% agreement rate,
  5/5 critical failure detection, 100% score accuracy (±1) on 22 hand-labeled examples.

## [0.1.2] — 2026-05-22

### Fixed

- `verdict eval` crashed with `ValidationError` at the report generation step due to
  `cost_breakdown['harness']` missing `estimated_cost_usd` (calculator was writing
  `subtotal_usd`). Field renamed to match the schema validator.
- Demo script (`scripts/demo.sh`) no longer requires `pv` — typing animation is now
  pure bash.

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
