# CLAUDE.md

Verdict (`verdict-eval` on PyPI) is evaluation infrastructure for AI agents. The goal it is
working toward: answer **"Did this change make my agent worse?"** for prompt, skill,
tool-definition and model changes, the way CI does for code.

## Hard rules

- **IP boundary.** Personal project. No employer code, data, names or references, ever.
  Demos and fixtures use public or synthetic sample apps only.
- **Branches.** Work on feature branches only and open a PR. Never push to `main`, never merge
  without the owner's approval.
- **Every PR:** tests passing, ruff clean, and a short summary that reads well on a phone.
- **Light base install.** Heavy dependencies go in optional extras (`crewai` today; `ui` and
  `traces` planned). New base dependencies need a reason.
- **Security boundary.** Read `CONTRIBUTING.md` before touching
  `verdict/evals/attack_patterns/` or `verdict/agents/adaptive_generator.py`.

## Stack

- Python 3.11–3.13, Poetry (`pyproject.toml`, `poetry.lock`), pydantic v2, click, rich,
  anthropic SDK, PyYAML. Optional: CrewAI (`verdict-eval[crewai]`).
- Web UI (not packaged yet): `web/backend` FastAPI + SQLite (`store.py`), deps in
  `web/backend/requirements.txt`; `web/frontend` React 18 + Vite + TypeScript + Tailwind,
  SSE for live runs.
- Release: GitHub release → `.github/workflows/publish.yml` → PyPI via OIDC trusted publishing.

## Layout

```
verdict/
  cli.py             click entry point: eval | diff | calibrate | sample-size | flakiness |
                     compliance | trace-eval
  agents/            test_generator, executor, judge (XML-delimited, injection-resistant),
                     reporter (deterministic Python), trace_judge, adaptive_generator
  adapters/          TargetAdapter base (concurrency, timeout, caching) + built-ins
  ci/                `verdict diff --base/--head` and `verdict calibrate`: config, git, suite,
                     side runner, gate, calibration, Markdown
  stats/             bootstrap CI, proportions (Wilson, Fisher, bootstrap diff), agreement (κ),
                     nondeterminism (pass@k, pass^k, flaky, sample size)
  orchestration/     legacy adapter-vs-adapter diff (`--target-a/--target-b`)
  models/            pydantic schemas (TestPrompt → ExecutionResult → Judgment → EvalReport)
  compliance/        HIPAA / NIST AI RMF mapping
  caching/ costs/ observability/ analysis/ reports/ evals/ config/
web/                 FastAPI backend + React frontend
tests/               smoke/ unit/ security/ qa/ integration/
```

Target layout (future refactor, not done yet): `verdict/core` (dataset, judge, stats,
reporter), `verdict/cli` (run | diff | calibrate | watch), `verdict/ci`, `verdict/ui`.

## Commands

```bash
poetry install                       # dev setup (or: pip install -e . && pip install pytest ruff)
poetry run pytest                    # all non-LLM tests (pyproject sets -m 'not llm')
poetry run pytest tests/unit -q      # one suite
poetry run pytest -m llm             # live-API tests; needs ANTHROPIC_API_KEY
poetry run ruff check verdict tests  # lint (CI-blocking)
poetry run mypy verdict              # type check (CI runs it non-blocking)
```

CI (`.github/workflows/test.yml`) runs ruff, mypy (allowed to fail) and `pytest -m "not llm"`
on Python 3.11 and 3.12 with a fake API key.

## Conventions

- Tests must not call the network. Mark anything that needs a live model `@pytest.mark.llm`.
  Inject fakes (e.g. a judge function) instead of patching the SDK where possible.
- Statistics are stdlib-only (no numpy/scipy in the base install) and deterministic when seeded.
- New schema fields are optional with defaults so stored reports stay loadable.
- Markdown meant for PR comments: verdict first, regressions next, then failing cases; keep
  tables narrow enough for mobile.
