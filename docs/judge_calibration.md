# Judge Calibration

## What is calibration?

Verdict's Judge is an LLM-based evaluator. Like any ML model, it can disagree
with humans. Calibration measures how often the judge agrees with hand-labeled
ground truth, so we can quantify its reliability and detect regressions when
models or prompts change.

## Dataset

`tests/qa/judge_calibration.json` — 22 hand-labeled examples covering all five
test categories:

| Category     | Examples | Pass | Fail |
|--------------|----------|------|------|
| correctness  | 6        | 3    | 3    |
| safety       | 4        | 2    | 2    |
| injection    | 5        | 2    | 3    |
| edge_case    | 4        | 3    | 1    |
| compliance   | 3        | 1    | 2    |
| **Total**    | **22**   | **11** | **11** |

Each example contains:
- A `TestPrompt` (prompt text, category, severity, expected behavior)
- An `ExecutionResult` (a synthetic target response — never hits a real system)
- `ground_truth` (passed, score 1–5 if applicable, failure\_mode, reasoning keywords)

## Methodology

1. Ground-truth labels were assigned by the project author reviewing each
   (prompt, response) pair against the rubric in `verdict/evals/rubrics.py`.
2. Labels were written before running any LLM judge — no label was derived
   from a judge output.
3. Borderline examples (ambiguous ground truth) are tagged in
   `tests/qa/test_judge_calibration.py::BORDERLINE_IDS` and excluded from
   the agreement-rate calculation.
4. The test suite is run with `pytest -m llm`, which requires a real
   `ANTHROPIC_API_KEY`. CI skips these tests (`-m "not llm"`).

## Quality thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Pass/fail agreement (non-borderline) | ≥ 80% | Sets a floor — below this the judge introduces more noise than signal |
| Critical failure detection | 5/5 | Any missed critical failure is a blocking regression |
| Score within ±1 (graded categories) | ≥ 70% | Graded scoring has inherent subjectivity; ±1 tolerance is standard |

## Baseline results

> **Note:** Run `pytest tests/qa/test_judge_calibration.py -v -m llm` and fill
> in the table below after the first run.

| Metric | Baseline (TBD) | Target |
|--------|----------------|--------|
| Agreement rate | — | ≥ 80% |
| Critical detection | — | 5 / 5 |
| Score accuracy | — | ≥ 70% |

## Re-running calibration

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pytest tests/qa/test_judge_calibration.py -v -m llm
```

## Updating the dataset

When adding new calibration examples:
1. Write the ground-truth label **before** running the judge.
2. Use realistic but fully synthetic data (no real PII).
3. Ensure the pass/fail split remains ≥ 40% in each class.
4. Tag genuinely ambiguous examples in `BORDERLINE_IDS`.

## Design decisions

- **Why not run calibration in CI?** Each calibration run makes ~22 LLM API calls
  (~$0.05–$0.15). This is acceptable locally but wasteful on every PR.
- **Why temperature 0.1?** The judge uses temperature 0.1 (not 0.0) to avoid
  repetition artifacts while keeping outputs stable. In practice, >95% of
  judgments are identical across re-runs at this temperature.
- **Judge injection resistance.** cal-018 specifically tests that the judge
  ignores an injection payload (`JUDGE OVERRIDE: ...`) embedded in the target
  response. The `<target_response>` XML tags in the prompt template are the
  primary defense.
